# eCourts Case Scraper (Headless Selenium)

This Python tool automates the process of fetching case details from the official [eCourts India](https://services.ecourts.gov.in/ecourtindia_v6/) website.

It runs completely headlessly using Selenium + BeautifulSoup, automatically saves valid CAPTCHA images, and extracts useful data such as:

- Case details
- Case status
- Petitioner/Respondent info
- Hearing dates
- Downloadable court documents (PDF/DOC)

---

# Features

1. Headless Chrome automation  
2. Automatic CAPTCHA saving (ensures non-empty)  
3. Extracts all structured case info  
4. Saves results in HTML, JSON, and TXT formats  
5. Auto-downloads attached case documents  
6. Supports CNR search modes  

---

#Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/Vibek75/ecourts-scraper.git
   cd ecourts-scraper
