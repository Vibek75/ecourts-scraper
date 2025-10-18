#!/usr/bin/env python3
import os
import sys
import time
import json
import re
import argparse
import urllib.parse
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import base64

import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

BASE_URL = "https://services.ecourts.gov.in/ecourtindia_v6/"
OUTPUT_DIR = "ecourts_output"
WAIT_SECONDS = 18
TIMEZONE = "Asia/Kolkata"

os.makedirs(OUTPUT_DIR, exist_ok=True)

def start_browser():
    opts = ChromeOptions()
    opts.add_argument("--headless=new")
    opts.add_argument("--window-size=1200,900")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
    service = ChromeService(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=opts)

def fetch_valid_captcha(driver):
    sess = requests.Session()
    for c in driver.get_cookies():
        sess.cookies.set(c['name'], c['value'])

    captcha_img = None
    for _ in range(10):
        imgs = driver.find_elements(By.TAG_NAME, "img")
        for im in imgs:
            try:
                src = im.get_attribute("src")
            except Exception:
                continue
            if not src:
                continue
            if "captcha" in src.lower() or "securimage" in src.lower():
                captcha_img = im
                break
        if captcha_img:
            break
        time.sleep(0.5)

    if not captcha_img:
        print("CAPTCHA image not found.")
        return None, sess

    for _ in range(10):
        src = captcha_img.get_attribute("src")
        if src and (src.startswith("data:") or src.strip()):
            break
        time.sleep(0.5)
    if not src:
        print("CAPTCHA src not available.")
        return None, sess

    path = None
    if src.startswith("data:"):
        try:
            header, b64 = src.split(",", 1)
            data = base64.b64decode(b64)
            if len(data) < 100:
                return None, sess
            path = os.path.join(OUTPUT_DIR, f"captcha_{int(time.time())}.png")
            with open(path, "wb") as f:
                f.write(data)
        except Exception:
            return None, sess
    else:
        try:
            if src.startswith("//"):
                src = "https:" + src
            elif src.startswith("/"):
                src = urllib.parse.urljoin(BASE_URL, src)
            r = sess.get(src, headers={"User-Agent":"Mozilla/5.0"}, timeout=20)
            if r.ok and r.content and len(r.content) > 100:
                path = os.path.join(OUTPUT_DIR, f"captcha_{int(time.time())}.png")
                with open(path, "wb") as f:
                    f.write(r.content)
        except Exception:
            return None, sess

    return path, sess

def find_input(driver, ids_or_names):
    for ident in ids_or_names:
        try:
            el = driver.find_element(By.ID, ident)
            return el
        except Exception:
            pass
        try:
            el = driver.find_element(By.NAME, ident)
            return el
        except Exception:
            pass
    return None

def submit_search(driver):
    candidates = [
        ("id", "searchbtn"), ("id", "searchBtn"),
        ("xpath", "//button[@type='submit']"),
        ("xpath", "//button[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'search')]"),
        ("xpath", "//input[@type='submit']")
    ]
    for typ, val in candidates:
        try:
            btn = driver.find_element(By.ID, val) if typ == "id" else driver.find_element(By.XPATH, val)
            try:
                btn.click()
            except:
                driver.execute_script("arguments[0].click();", btn)
            return True
        except:
            continue
    try:
        inputs = driver.find_elements(By.XPATH, "//input[@type='text']")
        if inputs:
            form = inputs[0].find_element(By.XPATH, "./ancestor::form")
            driver.execute_script("arguments[0].submit();", form)
            return True
    except:
        return False
    return False

def download_documents(html, driver=None):
    soup = BeautifulSoup(html, "lxml")
    docs = []
    sess = requests.Session()
    if driver:
        for c in driver.get_cookies():
            sess.cookies.set(c['name'], c['value'])
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if any(ext in href.lower() for ext in [".pdf",".doc",".docx",".xls",".xlsx",".rtf"]) or "download" in href.lower():
            url = urllib.parse.urljoin(BASE_URL, href) if href.startswith("/") else href
            try:
                r = sess.get(url, headers={"User-Agent":"Mozilla/5.0"}, timeout=30)
                if r.ok and r.content:
                    fname = os.path.basename(urllib.parse.urlparse(url).path) or f"doc_{int(time.time())}.bin"
                    outpath = os.path.join(OUTPUT_DIR, fname)
                    with open(outpath,"wb") as f:
                        f.write(r.content)
                    docs.append(outpath)
            except:
                continue
    return docs

def parse_result_html(html):
    soup = BeautifulSoup(html, "lxml")
    result = {}

    details = {}
    dtable = soup.find("table", class_=lambda c: c and "case_details_table" in c)
    if dtable:
        for tr in dtable.find_all("tr"):
            tds = tr.find_all(["td","th"])
            if len(tds)>=2:
                details[tds[0].get_text(" ",strip=True)] = tds[1].get_text(" ",strip=True)
    result["case_details"] = details

    status = {}
    stable = soup.find("table", class_=lambda c: c and "case_status_table" in c)
    if stable:
        for tr in stable.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds)>=2:
                status[tds[0].get_text(" ",strip=True)] = tds[1].get_text(" ",strip=True)
    result["case_status"] = status

    pet = []
    ptable = soup.find("table", class_=lambda c: c and "Petitioner_Advocate_table" in c)
    if ptable:
        for tr in ptable.find_all("tr"):
            txt = tr.get_text(" ", strip=True)
            if txt:
                pet.append(txt)
    result["petitioner_advocate"] = pet

    resp = []
    rtable = soup.find("table", class_=lambda c: c and "Respondent_Advocate_table" in c)
    if rtable:
        for tr in rtable.find_all("tr"):
            txt = tr.get_text(" ", strip=True)
            if txt:
                resp.append(txt)
    result["respondent_advocate"] = resp

    text = soup.get_text(" ", strip=True)
    date_patterns = [r"\b\d{1,2}[-/\.]\d{1,2}[-/\.]\d{2,4}\b",
                     r"\b\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{4}\b",
                     r"\b\d{4}-\d{1,2}-\d{1,2}\b"]
    found_dates = []
    for pat in date_patterns:
        for m in re.finditer(pat,text,re.IGNORECASE):
            s = m.group()
            try:
                d = dateparser.parse(s,dayfirst=True).date()
                found_dates.append({"raw": s, "date": d.isoformat()})
            except:
                continue
    
    nd, seen = [], set()
    for it in found_dates:
        if it["date"] not in seen:
            nd.append(it)
            seen.add(it["date"])
    result["found_dates"] = nd

    return result

def check_dates(parsed):
    tz = ZoneInfo(TIMEZONE)
    today = datetime.now(tz).date()
    tomorrow = today + timedelta(days=1)
    res = {"today": False, "tomorrow": False, "matches":[]}
    for d in parsed.get("found_dates",[]):
        dt = datetime.fromisoformat(d["date"]).date()
        if dt==today:
            res["today"]=True
            res["matches"].append({"raw":d["raw"],"date":d["date"],"which":"today"})
        if dt==tomorrow:
            res["tomorrow"]=True
            res["matches"].append({"raw":d["raw"],"date":d["date"],"which":"tomorrow"})
    return res

def run_search(args):
    driver = start_browser()
    driver.get(BASE_URL)
    time.sleep(1)

    captcha_path, sess = fetch_valid_captcha(driver)
    if not captcha_path:
        print("Captcha not fetched or blank. Exiting.")
        driver.quit()
        return

    captcha_text = input("Enter CAPTCHA text (from saved image): ").strip()

    if args.cnr:
        cnr_field = find_input(driver, ["cino","cnrNo","cnr","cinoNo","cinumber"])
        if not cnr_field:
            cnr_field = driver.find_elements(By.XPATH,"//input[@type='text']")[0]
        cnr_field.clear()
        cnr_field.send_keys(args.cnr)
    else:
        mapping = {"case_type":["case_type","ctype","case_type_id"],
                   "case_number":["case_no","case_number","cino","filing_no","filingnumber"],
                   "case_year":["case_year","year","filing_year"],
                   "state":["state_code","state"], "district":["dist_code","district"]}
        for key, opts in mapping.items():
            val = getattr(args,key,None)
            if val:
                field = find_input(driver, opts)
                if field:
                    field.clear()
                    field.send_keys(str(val))

    captcha_field = find_input(driver, ["fcaptcha_code","captcha_code","captcha","captchaCode","fcaptcha"])
    if captcha_field:
        captcha_field.clear()
        captcha_field.send_keys(captcha_text)

    if not submit_search(driver):
        if captcha_field:
            captcha_field.send_keys("\n")
    
    try:
        WebDriverWait(driver, WAIT_SECONDS).until(
            lambda d: d.find_elements(By.CSS_SELECTOR,"table.case_details_table") or
                      d.find_elements(By.CSS_SELECTOR,"table.case_status_table")
        )
    except:
        pass

    html = driver.page_source
    
    ts = int(time.time())
    html_path = os.path.join(OUTPUT_DIR,f"case_result_{ts}.html")
    with open(html_path,"w",encoding="utf-8") as f:
        f.write(html)

    parsed = parse_result_html(html)
    json_path = os.path.join(OUTPUT_DIR,f"case_result_{ts}.json")
    with open(json_path,"w",encoding="utf-8") as f:
        json.dump(parsed,f,ensure_ascii=False,indent=4)

    txt_path = os.path.join(OUTPUT_DIR,f"case_result_{ts}.txt")
    with open(txt_path,"w",encoding="utf-8") as f:
        for k,v in parsed.items():
            f.write(f"{k}:\n{v}\n\n")

    docs = download_documents(html, driver)
    print(f"Saved HTML: {html_path}, JSON: {json_path}, TXT: {txt_path}, Documents: {docs}")
    driver.quit()

def cli():
    parser = argparse.ArgumentParser(description="Improved eCourts Scraper")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--cnr", help="CNR number")
    group.add_argument("--case", action="store_true", help="Use Case Type/Number/Year")
    parser.add_argument("--case_type", help="Case Type")
    parser.add_argument("--case_number", help="Case Number")
    parser.add_argument("--case_year", help="Case Year")
    parser.add_argument("--state", help="State code")
    parser.add_argument("--district", help="District code")
    return parser.parse_args()

if __name__=="__main__":
    args = cli()
    if args.case:
        if not (args.case_type and args.case_number and args.case_year):
            print("Must supply --case_type, --case_number and --case_year")
            sys.exit(1)
    run_search(args)