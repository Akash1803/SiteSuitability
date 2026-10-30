"""TNReginet guideline-value (GLV) survey-wise search, driven with Selenium (headless Chrome).
Ported from the Reginet script used for Perungalathur / Kattupakkam: popup + 'session expired' recovery, retries, pagination."""
import subprocess
import time

URL = "https://tnreginet.gov.in/portal/webHP?requestType=ApplicationRH&actionVal=homePage&screenId=114&UserLocaleID=en"


class SessionExpired(Exception):
    pass


def _err(e):
    """error text with its message (repr of a selenium exception drops the message, e.g. the 403 from TNReginet)"""
    m = (getattr(e, "msg", None) or str(e) or "").strip().replace("Message: ", "")
    return f"{type(e).__name__}: {m}" if m else type(e).__name__


class Reginet:
    def __init__(self, show=False, log=print):
        self.show, self.log, self.d, self.w = show, log, None, None

    # ---------- browser ----------
    def start(self):
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.support.ui import WebDriverWait
        o = webdriver.ChromeOptions()
        if not self.show:
            o.add_argument("--headless=new")
            o.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
        o.add_argument("--window-size=1920,1080"); o.add_argument("--disable-blink-features=AutomationControlled")
        o.add_experimental_option("excludeSwitches", ["enable-automation"]); o.add_experimental_option("useAutomationExtension", False)
        svc = Service(popen_kw={"creation_flags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)})
        self.d = webdriver.Chrome(service=svc, options=o)
        self.d.set_page_load_timeout(60)        # the home page sometimes hangs for minutes: fail and start again instead
        self.d.get(URL); self.close_popup(); self.close_smoke(2)
        self.w = WebDriverWait(self.d, 40)

    def quit(self):
        try:
            if self.d:
                self.d.quit()
        except Exception:
            pass
        self.d = None

    def ensure(self):
        if self.d is None:
            self.start()

    # ---------- popups ----------
    def close_popup(self, wait=2):
        from selenium.webdriver.common.by import By
        from selenium.webdriver.common.keys import Keys
        time.sleep(wait)
        for by, sel in [(By.CSS_SELECTOR, ".modal .close"), (By.CSS_SELECTOR, ".modal-header .close"), (By.XPATH, "//button[normalize-space(text())='×']")]:
            for el in self.d.find_elements(by, sel):
                try:
                    if el.is_displayed():
                        self.d.execute_script("arguments[0].click();", el); time.sleep(1); return
                except Exception:
                    pass
        try:
            self.d.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
        except Exception:
            pass

    def smoke_open(self):
        from selenium.webdriver.common.by import By
        try:
            for el in self.d.find_elements(By.CSS_SELECTOR, ".smoke-base.smoke-visible"):
                if el.is_displayed():
                    return el
        except Exception:
            pass
        return None

    def close_smoke(self, timeout=3):
        from selenium.webdriver.common.by import By
        msgs, end = [], time.time() + timeout
        while time.time() < end:
            p = self.smoke_open()
            if p is None:
                if msgs:
                    break
                time.sleep(0.3); continue
            try:
                try:
                    msgs.append(p.find_element(By.CSS_SELECTOR, ".dialog-inner").text.strip().split("\n")[0])
                except Exception:
                    msgs.append("unknown")
                b = p.find_elements(By.CSS_SELECTOR, "button[id^='alert-ok'], .dialog-buttons button")
                if b:
                    self.d.execute_script("arguments[0].click();", b[0])
                else:
                    self.d.execute_script("arguments[0].classList.remove('smoke-visible');", p)
            except Exception:
                pass
            time.sleep(0.5)
        return "; ".join(msgs) if msgs else None

    def expired(self):
        from selenium.webdriver.common.by import By
        for xp in ("//*[contains(text(),'Go to home page')]", "//*[contains(text(),'session has expired')]", "//*[contains(text(),'காலாவதியாகி')]"):
            try:
                if any(e.is_displayed() for e in self.d.find_elements(By.XPATH, xp)):
                    return True
            except Exception:
                pass
        return False

    def recover(self):
        try:
            self.d.get(URL); self.close_popup(); self.close_smoke(1)
            if not self.expired():
                return
        except Exception:
            pass
        self.quit(); self.start()

    # ---------- dropdowns ----------
    def _survey_mode(self):
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC
        self.ensure()
        if self.expired():
            self.recover()
        self.close_popup(wait=0); self.close_smoke(0.3)       # the welcome popup only comes with a fresh page load
        self.w.until(EC.element_to_be_clickable((By.ID, "surveyRadio"))).click()

    def _select(self, chain):
        """chain: [(dropdown id, value)], each waits for its options (re-fires the previous onchange on a website error)."""
        from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.support.ui import Select, WebDriverWait
        for i, (did, val) in enumerate(chain):
            for attempt in range(3):
                dd = self.w.until(EC.presence_of_element_located((By.ID, did)))
                try:
                    WebDriverWait(self.d, 20, ignored_exceptions=(StaleElementReferenceException,)).until(
                        lambda d: self.smoke_open() is not None or self.expired() or len(Select(dd).options) > 1)
                except TimeoutException:
                    pass
                if self.expired():
                    raise SessionExpired(did)
                msg = self.close_smoke(1)
                if msg is None and len(Select(dd).options) > 1:
                    if val is not None:
                        Select(dd).select_by_value(val); time.sleep(0.5)
                    break
                if attempt == 2:
                    raise TimeoutException(f"{did} options never loaded ({msg})")
                if i > 0:
                    prev = self.d.find_element(By.ID, chain[i - 1][0])
                    self.d.execute_script("arguments[0].dispatchEvent(new Event('change', {bubbles: true}));", prev)
                time.sleep(2)

    def options(self, did):
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import Select
        return [(o.get_attribute("value"), o.text.strip()) for o in Select(self.d.find_element(By.ID, did)).options
                if o.get_attribute("value") not in ("", "0", "-1", None) and "select" not in o.text.lower()]

    def list_villages(self, zone):
        """[(sro_id, sro_name, village_id, village_name)] for one revenue district (zone)."""
        out = []
        for attempt in range(4):   # TNReginet answers 403 now and then for a few minutes: start again on a fresh page, waiting longer each time
            try:
                self._survey_mode(); self._select([("districtList", zone), ("SROList", None)])
                break
            except Exception as e:
                if attempt == 3:
                    raise
                self.log(f"  SRO list of district {zone}: {_err(e)[:100]} - trying again in {30 * (attempt + 1)} s")
                self.quit(); time.sleep(30 * (attempt + 1))
        sros = self.options("SROList")
        for sid, sname in sros:
            for attempt in range(2):
                try:
                    self._survey_mode(); self._select([("districtList", zone), ("SROList", sid), ("villageList", None)])
                    out += [(sid, sname, vid, vname) for vid, vname in self.options("villageList")]
                    break
                except Exception as e:
                    self.log(f"  SRO {sname}: {_err(e)[:100]} - retrying"); self.recover()
        return out

    # ---------- survey search ----------
    def survey(self, zone, sro, village, survey):
        """-> (status, [ {Subdivision Number, Guideline_Value_British, Guideline_Value_Metric, Land_Classification, Effective_Start_Date} ])"""
        from selenium.common.exceptions import NoSuchElementException, StaleElementReferenceException
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC
        rows = []
        try:
            self._survey_mode()
            self._select([("districtList", zone), ("SROList", sro), ("villageList", village)])
            err = None
            for attempt in range(2):
                box = self.d.find_element(By.ID, "surveyName"); box.clear(); box.send_keys(survey)
                self.d.execute_script("guideLineSearchDiv();")
                self.w.until(EC.any_of(EC.presence_of_element_located((By.ID, "searchTable")),
                                       EC.presence_of_element_located((By.XPATH, "//*[contains(text(),'Nothing Found')]")),
                                       lambda d: self.smoke_open(), lambda d: self.expired()))
                if self.expired():
                    raise SessionExpired("after search")
                err = self.close_smoke(0.5)
                if err is None:
                    break
                time.sleep(2)
            if err:
                status = f"Website Error: {err}"
            elif self.d.find_elements(By.XPATH, "//*[contains(text(),'Nothing Found')]"):
                status = "Nothing Found"
            else:
                while True:
                    try:
                        trs = self.w.until(EC.presence_of_all_elements_located((By.XPATH, "//table[@id='searchTable']/tbody/tr")))
                        # the whole page in one script call (cell by cell through the driver took seconds per page)
                        cells = self.d.execute_script("return Array.from(document.querySelectorAll('#searchTable tbody tr'))"
                                                      ".map(tr => Array.from(tr.querySelectorAll('td')).map(td => td.innerText.trim()))")
                        for td in cells:
                            if len(td) >= 6:
                                rows.append({"Subdivision Number": td[1], "Guideline_Value_British": td[2], "Guideline_Value_Metric": td[3],
                                             "Land_Classification": td[4], "Effective_Start_Date": td[5]})
                        try:
                            nb = self.d.find_element(By.LINK_TEXT, "Next")
                            if "disabled" in (nb.get_attribute("class") or "") or not nb.is_displayed():
                                break
                            first = trs[0]; nb.click(); self.w.until(EC.staleness_of(first))
                        except NoSuchElementException:
                            break
                    except StaleElementReferenceException:
                        continue
                status = "Success" if rows else "Error: no rows"
            try:
                b = self.w.until(EC.element_to_be_clickable((By.ID, "backFeedBack"))); self.d.execute_script("arguments[0].click();", b)
            except Exception:
                self.d.get(URL); self.close_popup(); self.close_smoke(1)
            return status, rows
        except SessionExpired as e:
            self.recover(); return f"Error: session expired ({e})", []
        except Exception as e:
            self.quit(); return f"Error: {_err(e)[:150]}", []
