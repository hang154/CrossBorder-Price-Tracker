"""Home-first smoke test with an isolated local Chrome and its own driver/profile.
Does not reuse login cookies, alter the user's Chrome or solve CAPTCHAs.
"""
import argparse,datetime as dt,hashlib,json,os,re,tempfile,time
from pathlib import Path
import setuptools  # supplies distutils for the legacy driver on Python 3.14
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from app.sourcing_pipeline import atomic_json
from app.isolated_display import virtual_display

HOME='https://www.coupang.com/'
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--out',required=True,type=Path);ap.add_argument('--headless',action='store_true');args=ap.parse_args();out=args.out;out.mkdir(parents=True,exist_ok=True)
 t=time.monotonic();result={'started_at_kst':dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(),'profile':'isolated_temporary_no_imported_cookies','headless':args.headless,'artificial_delay_seconds':0,'observations':[],'home_ready':False,'details_complete':0,'monthly_reviews_complete':0};driver=None;display=None
 try:
  os.nice(19);display=virtual_display();result['virtual_display']=display.__enter__()
  with tempfile.TemporaryDirectory(prefix='cpvb-profile-',dir='/tmp',ignore_cleanup_errors=True) as profile:
   options=uc.ChromeOptions();options.add_argument('--disable-dev-shm-usage');options.add_argument('--no-first-run');options.add_argument('--no-default-browser-check');options.add_argument('--ozone-platform=x11');options.add_argument('--window-size=1280,900')
   try:
    driver=uc.Chrome(options=options,browser_executable_path='/usr/bin/google-chrome',version_main=143,user_data_dir=profile,headless=args.headless,use_subprocess=True);driver.set_page_load_timeout(25)
    for i in range(1,4):
     error=None
     try:driver.get(HOME)
     except Exception as e:error=type(e).__name__+': '+str(e).splitlines()[0]
     body=driver.page_source;title=driver.title;blocked=bool(re.search(r'access denied|captcha|verify you are human|비정상적인 접근|접속이.*제한',title+' '+driver.find_element(By.TAG_NAME,'body').text[:2000],re.I));inputs=[e for e in driver.find_elements(By.CSS_SELECTOR,'input#headerSearchKeyword,input[name="q"]') if e.is_displayed()]
     row={'attempt':i,'url':driver.current_url,'title':title,'blocked':blocked,'search_input_visible':bool(inputs),'source_sha256':hashlib.sha256(body.encode()).hexdigest(),'bytes':len(body.encode()),'error':error};result['observations'].append(row);(out/f'home-{i}.html').write_text(body);atomic_json(out/'result.json',result)
     if not blocked and inputs:result['home_ready']=True;driver.save_screenshot(str(out/'home.png'));break
    if result['home_ready']:
     field=inputs[0];field.clear();field.send_keys('Arsjuo 규조토 발매트');button=field.find_element(By.XPATH,'ancestor::form').find_element(By.CSS_SELECTOR,'button[type=submit],input[type=submit]');button.click();WebDriverWait(driver,20).until(lambda d:'/np/search' in d.current_url or 'Access Denied' in d.title);body=driver.page_source;(out/'search.html').write_text(body);result['search']={'url':driver.current_url,'title':driver.title,'target_link_observed':bool(driver.find_elements(By.CSS_SELECTOR,'a[href*="/vp/products/8732259896"]')),'sha256':hashlib.sha256(body.encode()).hexdigest()}
     links=driver.find_elements(By.CSS_SELECTOR,'a[href*="/vp/products/8732259896"]')
     if links:
      driver.execute_script("arguments[0].target='_self'",links[0]);links[0].click();WebDriverWait(driver,20).until(lambda d:'/vp/products/' in d.current_url);body=driver.page_source;(out/'detail-shell.html').write_text(body);result['detail']={'url':driver.current_url,'title':driver.title,'description_present':bool(driver.find_elements(By.CSS_SELECTOR,'.product-detail-content')),'sha256':hashlib.sha256(body.encode()).hexdigest()}
   finally:
    if driver:driver.quit();driver=None
 except Exception as exc:result['error']=type(exc).__name__+': '+str(exc)[:600]
 finally:
  if driver:
   try:driver.quit()
   except Exception:pass
  if display:
   try:display.__exit__(None,None,None);result['virtual_display_removed']=True
   except Exception as exc:result['display_cleanup_error']=str(exc)[:300]
  result['elapsed_seconds']=round(time.monotonic()-t,3);result['finished_at_kst']=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat();atomic_json(out/'result.json',result);print(json.dumps(result,ensure_ascii=False),flush=True)
 return 0 if result.get('detail',{}).get('description_present') else 3
if __name__=='__main__':raise SystemExit(main())
