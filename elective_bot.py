import requests
import random
import io
import time
import threading
import tkinter
import numpy as np
from tkinter import ttk, messagebox
from bs4 import BeautifulSoup
from PIL import Image, ImageTk
import hashlib

import captcha
from logger import Logger,log_q

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

TIMEOUT_S=30

auth={
    'username': None,
    'password': None,
    'channel': None,
}

class ElectiveBot:
    def __init__(self,name):
        adapter=requests.adapters.HTTPAdapter(pool_connections=1,pool_maxsize=1,pool_block=True)
        self.s=requests.Session()
        self.s.mount('http://elective.pku.edu.cn',adapter)
        self.s.mount('https://elective.pku.edu.cn',adapter)
        self.s.verify=False
        self.s.trust_env=True
        self.s.headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36',
            'Referer': 'https://elective.pku.edu.cn/elective2008/edu/pku/stu/elective/controller/help/HelpController.jpf',
            'Cache-Control': 'max-age=0',
        }

        self._status='init'
        self.name=name
        self.log=Logger(name)
        self.last_loop_time=time.time()

    @property
    def status(self):
        return self._status
    @status.setter
    def status(self,s):
        self._status=s
        log_q.put(None)

    def auth(self):
        assert auth['username'] and auth['password'], 'credential not set'
        self.log('debug','before auth')

        res=self.s.post(
            'https://iaaa.pku.edu.cn/iaaa/oauthlogin.do',
            data={
                'appid': 'syllabus',
                'userName': auth['username'],
                'password': auth['password'],
                'randCode': '',
                'smsCode': '',
                'otpCode': '',
                'redirUrl': 'http://elective.pku.edu.cn:80/elective2008/agent4Iaaa.jsp/../ssoLogin.do'
            },
            cookies={
                'userName': auth['username'],
            },
        )
        res.raise_for_status()
        json=res.json()
        assert json['success'], json
        token=json['token']
        self.log('debug',f'get auth token {token}')

        res=self.s.get(
            'https://elective.pku.edu.cn/elective2008/ssoLogin.do',
            params={
                'rand': '%.10f'%random.random(),
                'token': token,
            },
        )
        res.raise_for_status()
        if '<title>帮助-总体流程</title>' not in res.text:
            if '/scnStAthVef.jsp/' in res.text:
                if not auth['channel']:
                    raise RuntimeError('需要身份信息，参见 README')
                else:
                    sida=res.text.partition('/ssoLogin.do?sida=')[2].partition('&')[0]
                    assert sida.isalnum(), 'invalid sida'
                    
                    self.log('debug','choose channel %s for sida %s'%(auth['channel'],sida))
                    
                    res=self.s.get(
                        'https://elective.pku.edu.cn/elective2008/ssoLogin.do',
                        params={
                            'sida': sida,
                            'sttp': auth['channel'],
                        },
                    )
                    res.raise_for_status()
                    if '<title>帮助-总体流程</title>' not in res.text:
                        raise RuntimeError('after login check failed')
                    
            else:
                raise RuntimeError('after login check failed')

    def proc_course_elem(self,rows):
        for row in rows:
            name=row.select('td:nth-of-type(1) span')[0].get_text()
            classid=row.select('td:nth-of-type(6) span')[0].get_text()
            teacher=row.select('td:nth-of-type(5) span')[0].get_text()
            selectbtn=(row.select('a[href^="/elective2008/edu/pku/stu/elective/controller/supplement/electSupplement.do"]') or [None])[0]

            volume_cnt,_,elected_cnt=row.select('td span[id^="electedNum"]')[0].get_text(strip=True).partition(' / ')
            if '/' in elected_cnt:
                elected_cnt=elected_cnt.partition('/')[0]

            volume_cnt=int(volume_cnt)
            elected_cnt=int(elected_cnt)
            if elected_cnt==0: # buggy
                elected_cnt=volume_cnt
                self.log('warning',f'loop got buggy elected count for {name}')

            if not selectbtn: # already chosen
                continue

            yield {
                'name': name,
                'classid': classid,
                'teacher': teacher,
                'selecturl': f'https://elective.pku.edu.cn{selectbtn.attrs["href"]}',
                'volume_cnt': volume_cnt,
                'elected_cnt': elected_cnt,
            }

    @staticmethod
    def detect_err(soup):
        fatal_err_elems=soup.select('td[background="/elective2008/resources/images/11-1.png"] td.black')
        if fatal_err_elems:
            return fatal_err_elems[0].get_text(strip=True)
    @staticmethod
    def detect_tips(soup):
        tips_elems=soup.select('#msgTips td[width="100%"]')
        if tips_elems:
            return tips_elems[0].get_text(strip=True)

    def loop_(self,url=None):
        if url is None:
            url = f'https://elective.pku.edu.cn/elective2008/edu/pku/stu/elective/controller/supplement/SupplyCancel.do?xh={auth["username"]}'
        
        self.log('debug',f'loop get {url}')
        res=self.s.get(
            url,
            params={'xh': auth['username']},
            timeout=TIMEOUT_S,
        )
        res.raise_for_status()

        soup=BeautifulSoup(res.text,'lxml')

        fatal_err=self.detect_err(soup)
        if fatal_err:
            if '目前不是补退选时间' not in fatal_err and '目前是跨院系选课数据准备时间' not in fatal_err and '目前时段不能选课' not in fatal_err:
                self.status='dead'
            self.log('critical', f'loop fatal err {fatal_err}')
            return

        if soup.title.get_text()!='补选退选':
            self.status='dead'
            self.log('critical',f'loop title is {soup.title}')
            return

        courses=list(self.proc_course_elem(soup.select('tr.datagrid-all, tr.datagrid-odd, tr.datagrid-even')))

        # fixme
        next_link=soup.find('a',text='Next')
        if not next_link:
            return courses
        else:
            try:
                next=self.loop_(f'https://elective.pku.edu.cn{next_link.attrs["href"]}')
                return courses+next
            except Exception as e:
                self.log('warning', f'loop error {type(e)} {str(e)}')
                return courses

    def loop(self,callback_fatal):
        self.status='loop'
        self.last_loop_time=time.time()
        try:
            res=self.loop_() or []
        except Exception as e:
            self.log('warning',f'loop error {type(e)} {str(e)}')
            return []
        else:
            if res:
                self.log('info','loop ok')
            return res
        finally:
            if self.status=='dead':
                callback_fatal()
            else:
                self.status='idle'

    def get_captcha(self):
        try:
            self.log('debug','get captcha')
            res=self.s.get(
                'https://elective.pku.edu.cn/elective2008/DrawServlet',
                params={
                    'Rand': '%.10f'%(10000*random.random()),
                },
                timeout=TIMEOUT_S,
            )
            res.raise_for_status()
            return Image.open(io.BytesIO(res.content))
        except Exception as e:
            self.log('warning',f'get captcha error {type(e)} {str(e)}')
            return Image.open('error.gif')

    def verify_captcha(self,captcha):
        try:
            self.log('debug',f'check captcha {captcha}')
            res=self.s.post(
                'https://elective.pku.edu.cn/elective2008/edu/pku/stu/elective/controller/supplement/validate.do',
                data={
                    'validCode': captcha,
                    'xh': auth['username'],
                },
                timeout=TIMEOUT_S,
            )
            res.raise_for_status()
            assert res.json()['valid']=='2', res.json()
            return True
        except Exception as e:
            self.log('warning',f'bad captcha {type(e)} {str(e)}')
            return False

    def enter_captcha(self,tk,should_autoinput=False):
        if should_autoinput:
            self.log('info','doing auto captcha')
            try:
                img=self.get_captcha()
                self.log('debug',f'downloaded captcha')
                result=captcha.recognize(img)
                self.log('debug',f'recognized captcha {result}')
                assert self.verify_captcha(result), 'incorrect captcha'
            except Exception as e:
                raise RuntimeError(f'captcha recognize error {type(e)} {str(e)}')
            else:
                self.log('info','auto captcha verify ok')
                self.status='idle'
                return
            
        else:
            self.log('info','doing manual captcha')
        
            tl=tkinter.Toplevel(tk)
            try:
                tl.wm_attributes('-toolwindow',True)
            except Exception: # toolwindow only works on Windows
                pass
            tl.title(f'Captcha for {self.name}')

            captcha_var=tkinter.StringVar(tl)

            label=ttk.Label(tl)
            label.pack()

            def submit_captcha():
                if self.verify_captcha(captcha_var.get()):
                    self.log('info','captcha verify ok')
                    tl.destroy()
                    self.status='idle'
                else:
                    messagebox.showerror('Error', 'Incorrect captcha')
                    entry.focus_set()

            def skip_captcha():
                img=self.get_captcha()
                #img.seek(15)
                label._image=ImageTk.PhotoImage(img)
                label['image']=label._image
                tl.update_idletasks()

            entry=ttk.Entry(tl,textvariable=captcha_var)
            entry.bind('<Return>',lambda _:submit_captcha())
            entry.pack()
            ttk.Button(tl,text='Next Captcha',command=skip_captcha).pack()

            entry.focus_set()
            tl.after_idle(skip_captcha)

    def select_(self,url):
        self.log('debug',f'select {url}')
        res=self.s.post(
            url,
            timeout=TIMEOUT_S,
        )
        res.raise_for_status()

        soup=BeautifulSoup(res.text,'lxml')

        fatal_err=self.detect_err(soup)
        if fatal_err:
            self.log('warning', f'select err {fatal_err}')
            return False, fatal_err

        tips=self.detect_tips(soup)
        if tips:
            if '成功，请查看已选上列表确认' in res.text:
                self.log('info',f'select ok {tips}')
                return True, tips
            else:
                self.log('warning',f'select fail {tips}')
                return False, tips
        else:
            self.log('warning','select no tips')
            return False, ''

    def select(self,url,callback=lambda *_: None):
        self.status='select'
        def do_select():
            try:
                ok,reason=self.select_(url)
            except Exception as e:
                reason=f'select err {type(e)} {str(e)}'
                self.log('warning',reason)
                callback(False,reason)
            else:
                callback(ok,reason)
            finally:
                self.status='idle'
        threading.Thread(target=do_select,daemon=True).start()