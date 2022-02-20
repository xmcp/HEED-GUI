from tkinter import *
from tkinter.ttk import *
from tkinter import messagebox, simpledialog
from tkinter.scrolledtext import ScrolledText
import threading
import os
import queue
import time
import random
import hashlib

from logger import Logger, log_q
from elective_bot import *
import captcha
from notifier import Notifier

tk=Tk()
tk.title('High Efficiency Elective Dominator')
tk.rowconfigure(1,weight=1)
tk.columnconfigure(0,weight=1)

tk.update_idletasks()

MIN_INTERVAL_MS=5000 # setting interval to zero will NOT make it faster, see README for more info

def tweak_intv_time(t):
    return int(t*.8+random.random()*t*.4)

class Orchestrator:
    INTERVAL_MS=3000

    def __init__(self):
        self.name='Orchestrator'
        self.status='idle'
        self.log=Logger(self.name)

        self.bot_id_top=0
        self.bots=[]
        self.courses=[]
        self.courses_display={}
        self.wishlist=[]
        self.wishlist_busy=set()
        self.preload_wishlist()

        self.wish_var=StringVar(tk)
        self.auto_captcha_var=StringVar(tk,value='off')
        self.update_wish_var()
        self.tree=None

        self.notifier=Notifier()

        self.init_main_window()
        self.update_wish_var()

        auth['username']=simpledialog.askstring('Auth',f'请先阅读README.md\n\nUsername:') or ''
        if '@' in auth['username']:
            auth['username'], _, auth['channel']=auth['username'].partition('@')
        else:
            auth['channel']=None
        auth['password']=simpledialog.askstring('Auth','Password:',show='*') or ''
        self.notifier.username=auth['username']

        self.init_logging_window()

        self.auto_id=None
        self.auto_on=False
        self.course_update_q=queue.Queue()
        threading.Thread(target=self.course_update_worker,daemon=True).start()

    def preload_wishlist(self): # format: 'name classid' each line
        if os.path.isfile('wishlist.txt'):
            self.log('info','preload wishlist')
            with open('wishlist.txt','r',encoding='utf-8') as f:
                lines=[(name,classid) for l in filter(None,f.read().split('\n')) for name,_,classid in [l.rpartition('|')]]
            self.wishlist=lines

    def remove_wishlist_by_name(self,target_name):
        for name,classid in self.wishlist[:]:
            if name==target_name:
                self.wishlist.remove((name,classid))
                self.log('info',f'remove from wishlist {name} {classid}')
        self.update_wish_var()

    def choose_bot(self):
        candidates=list(filter(lambda bot:bot.status=='idle',self.bots))
        if not candidates:
            self.log('warning','no idle bot')
            return None
        else:
            return min(candidates,key=lambda bot:bot.last_loop_time)

    def manual_select(self):
        cid=self.tree.focus()
        if cid and cid in self.courses_display:
            bot,course=self.courses_display[cid]
            if course['elected_cnt']<course['volume_cnt']:
                self.log('info',f'manual select {course["name"]} {course["classid"]}')

                if bot.status=='idle':
                    def callback(ok,reason):
                        self.log('success' if ok else 'warning',reason)
                        if ok:
                            self.remove_wishlist_by_name(course['name'])
                            
                    bot.select(course['selecturl'],callback)
                else:
                    self.log('warning',f'cannot select bot status is {bot.status}')
            else:
                info=(course['name'],course['classid'])
                if info in self.wishlist:
                    self.log('info', f'remove from wishlist {course["name"]} {course["classid"]}')
                    self.wishlist.remove(info)
                else:
                    self.log('info', f'add to wishlist {course["name"]} {course["classid"]}')
                    self.wishlist.append(info)
                self.update_wish_var()

    def add_bot(self):
        should_auto_captcha=self.auto_captcha_var.get()=='on'
        def do_add_bot():
            self.bot_id_top+=1
            name=f'Bot {self.bot_id_top}'
            self.log('info',f'add {name}')
            bot=ElectiveBot(name)
            self.bots.append(bot)
            log_q.put(None)
            try:
                bot.auth()
                bot.status='captcha'
                bot.enter_captcha(tk,should_auto_captcha)
            except Exception as e:
                self.log('warning',f'{bot.name} auth failed {type(e)} {str(e)}')
                self.bots.remove(bot)
                log_q.put(None)

        threading.Thread(target=do_add_bot).start()

    def on_bot_fatal(self,bot):
        if self.auto_captcha_var.get()=='on':
            while True:
                bot.log('warning',f'recovering from fatal error')
                try:
                    bot.status='recover'
                    bot.auth()
                    bot.status='captcha'
                    bot.enter_captcha(tk,True)
                except Exception as e:
                    bot.log('critical',f'{type(e)} {e}')
                    time.sleep(.5)
                else:
                    return
        else:
            self.log('critical', f'{bot.name} fatal error, removing')
            self.bots.remove(bot)
            self.notifier.report_bot_fatal(len(self.bots))

    def refresh(self):
        def work():
            bot=self.choose_bot()
            if bot:
                self.log('debug',f'start refresh job {bot.name}')
                courses=bot.loop(lambda: self.on_bot_fatal(bot))
                self.log('debug',f'refresh complete {bot.name}')
                self.course_update_q.put((bot,courses))
        threading.Thread(target=work,daemon=True).start()

        if self.auto_id:
            tk.after_cancel(self.auto_id)
        if self.auto_on:
            self.auto_id=tk.after(tweak_intv_time(self.INTERVAL_MS), self.refresh)

    def course_update_worker(self):
        last_succ_time=int(time.time())
        while True:
            bot,courses=self.course_update_q.get(block=True)
            if courses:
                self.update_course_list(bot,courses)
                self.check_wish(bot,courses)
                last_succ_time=int(time.time())
            else: # [] when failed
                self.log('debug','loop get no courses')
                self.notifier.report_refresh_failure(last_succ_time)

    def check_wish(self,bot,courses):
        courses=courses[:]
        random.shuffle(courses)

        for course in courses:
            in_wishlist=(
                ((course['name'], course['classid']) in self.wishlist) and
                ((course['name'], course['classid']) not in self.wishlist_busy)
            )
            if in_wishlist and course['elected_cnt']<course['volume_cnt']: # can auto select
                self.log('info',f'auto select {course["name"]} {course["classid"]}')

                shadowed_list=[(name,classid) for name,classid in self.wishlist if name==course['name']]
                self.wishlist_busy.update(shadowed_list)
                self.log('debug',f'shadowing {" ".join(map(repr,shadowed_list))}')
                self.update_wish_var()

                def callback(ok,reason):
                    if ok:
                        self.log('success',reason)
                        self.remove_wishlist_by_name(course['name'])
                        self.notifier.report_success_choice(course['name'])
                    else:
                        self.log('warning',reason)
                        self.notifier.report_failed_choice(course['name'], reason)

                    self.wishlist_busy.difference_update(shadowed_list)
                    self.update_wish_var()

                bot.select(course['selecturl'],callback)
                break # select only one course at once

    def init_logging_window(self): # logger requires: name, status, log
        tl=Toplevel(tk)
        tl.title('Logging Window')
        tl.rowconfigure(0,weight=1)
        tl.columnconfigure(1,weight=1)
        tl.protocol('WM_DELETE_WINDOW',lambda *_:None)
        tk.tkraise(tl)

        li_var=StringVar()
        li_items=[]
        cur_select=None

        def onselect(e):
            nonlocal cur_select
            nonlocal text_lid_begin
            nonlocal text_lid_end
            idxs=li.curselection()
            if len(idxs)==1:
                cur_select=li_items[idxs[0]]
                text.delete('1.0','end')
                text_lid_begin=0
                text_lid_end=0
                log_q.put(None)
                log_q.put(cur_select.name)
                tl.title(f'Logging Window - {cur_select.name}')

        li=Listbox(tl,listvariable=li_var)
        li.bind('<<ListboxSelect>>',onselect)
        li.grid(row=0,column=0,sticky='ns')
        text=ScrolledText(tl,width=70)
        text.grid(row=0,column=1,sticky='nswe')

        text.tag_config('time',foreground='black')
        text.tag_config('debug',foreground='gray')
        text.tag_config('info',foreground='blue')
        text.tag_config('warning',background='yellow')
        text.tag_config('success',background='#00ff00')
        text.tag_config('critical',background='red',foreground='white')

        text_lid_begin=0
        text_lid_end=0
        def render_worker():
            nonlocal li_items
            nonlocal text_lid_begin
            nonlocal text_lid_end
            while True:
                item=log_q.get(block=True)
                if item is None: # render list
                    sorted_bots=[x for x in self.bots if x.status!='dead']+[x for x in self.bots if x.status=='dead']
                    li_items=[self,self.notifier]+sorted_bots
                    li_var.set(tuple(f'{x.name} [{x.status}]' for x in li_items))
                elif cur_select is not None and item==cur_select.name: # render text
                    cs=cur_select
                    with cs.log.lock:
                        if text_lid_end:
                            delta=cs.log.lid_begin-text_lid_begin
                        else:
                            delta=0
                            text_lid_end=cs.log.lid_begin
                        for _ in range(delta):
                            text.delete('1.0','1.end')
                            text_lid_begin+=1
                        for i in range(text_lid_end,cs.log.lid_end):
                            try:
                                tim,typ,msg=cs.log.logs[i-cs.log.lid_begin]
                            except IndexError as e:
                                break
                            else:
                                text_lid_end+=1
                                text.insert('end',f'{time.strftime("%m-%d %H:%M:%S",time.localtime(tim))} ','time')
                                text.insert('end',f'[{typ}] {msg}',typ)
                                text.insert('end','\n')
                    text.see('end')

        threading.Thread(target=render_worker,daemon=True).start()
        log_q.put(None)

    def init_main_window(self):
        btnpanel=Frame(tk)
        btnpanel.grid(row=0,column=0,columnspan=3,sticky='we')

        def ref_changed():
            self.auto_on=auto_refresh_var.get()=='on'
            self.status='auto' if self.auto_on else 'idle'
            self.log('debug',f'auto change to {self.auto_on}')
            if self.auto_id:
                tk.after_cancel(self.auto_id)
            if self.auto_on:
                self.refresh()

        auto_captcha_var=self.auto_captcha_var
        auto_refresh_var=StringVar(tk,value='off')
        verbose_var=StringVar(tk,value='on' if Logger.VERBOSE else 'off')
        notif_var=StringVar(tk,value='on' if self.notifier.status=='on' else 'off')
        
        def on_quit(*_):
            if auto_refresh_var.get()=='on':
                self.log('critical','turn off auto refresh before quitting')
            else:
                tk.destroy()
        
        tk.protocol('WM_DELETE_WINDOW',on_quit)

        Button(btnpanel,text='Add Bot',command=self.add_bot).grid(row=0,column=0)
        Checkbutton(btnpanel,text='Captcha',variable=auto_captcha_var,onvalue='on',offvalue='off').grid(row=0,column=1)
        Button(btnpanel,text='Refresh',command=self.refresh).grid(row=0,column=2)
        Checkbutton(btnpanel,text='Auto',command=ref_changed,variable=auto_refresh_var,onvalue='on',offvalue='off').grid(row=0,column=3)

        interval_var=IntVar(tk,value=self.INTERVAL_MS)
        timeout_var=IntVar(tk,value=TIMEOUT_S*1000)

        def change_time_config(e):
            global TIMEOUT_S
            self.INTERVAL_MS=max(interval_var.get(),MIN_INTERVAL_MS)
            TIMEOUT_S=timeout_var.get()/1000
            self.log('info',f'change to interval {self.INTERVAL_MS}ms timeout {int(TIMEOUT_S*1000)}ms')

        Label(btnpanel,text=' Intv').grid(row=0,column=4)
        interval_entry=Entry(btnpanel,textvariable=interval_var,width=7)
        interval_entry.bind('<Return>',change_time_config)
        interval_entry.grid(row=0,column=5)
        Label(btnpanel,text=' Timeout').grid(row=0,column=6)
        timeout_entry=Entry(btnpanel,textvariable=timeout_var,width=7)
        timeout_entry.bind('<Return>',change_time_config)
        timeout_entry.grid(row=0,column=7)

        def verbose_changed():
            Logger.VERBOSE=verbose_var.get()=='on'
            self.log('info',f'verbose changed to {Logger.VERBOSE}')

        Checkbutton(btnpanel,text='Verbose',command=verbose_changed,variable=verbose_var,onvalue='on',offvalue='off').grid(row=0,column=8)
        
        def notif_changed():
            self.notifier.status=notif_var.get()
            log_q.put(None)
            self.log('info',f'notif changed to {self.notifier.status}')
            if self.notifier.status=='on':
                self.notifier.report_startup()
        
        Checkbutton(btnpanel,text='Notif',command=notif_changed,variable=notif_var,onvalue='on',offvalue='off').grid(row=0,column=9)

        self.tree=Treeview(tk,columns=('teacher','volume_cnt','elected_cnt','status'),height=20)
        self.tree.grid(row=1,column=0,sticky='nswe')

        sbar=Scrollbar(tk,orient=VERTICAL,command=self.tree.yview)
        sbar.grid(row=1,column=1,sticky='ns')
        self.tree.configure(yscrollcommand=sbar.set)

        self.tree.heading('volume_cnt',text='Volume')
        self.tree.heading('teacher',text='Teacher')
        self.tree.heading('elected_cnt',text='Elected')
        self.tree.heading('status',text='Status')

        self.tree.column('#0',width=250,anchor='w')
        self.tree.column('teacher',width=200,anchor='w')
        self.tree.column('volume_cnt',width=50,anchor='e')
        self.tree.column('elected_cnt',width=50,anchor='e')
        self.tree.column('status',width=80,anchor='e')

        self.tree.bind('<Double-Button-1>',lambda e: self.manual_select())

        def remove_wish(e):
            idxs=wish_box.curselection()
            if len(idxs)==1:
                course=self.wishlist[idxs[0]]
                self.log('info',f'remove from wishlist {course[0]} {course[1]}')
                del self.wishlist[idxs[0]]
                self.update_wish_var()

        wish_box=Listbox(tk,listvariable=self.wish_var)
        wish_box.bind('<Double-Button-1>',remove_wish)
        wish_box.grid(row=1,column=2,sticky='ns')

    def update_wish_var(self):
        self.wish_var.set(tuple(f'{"* " if course in self.wishlist_busy else ""}{course[0]} {course[1]}' for course in self.wishlist))

    def update_course_list(self,bot,courses):
        self.tree.delete(*self.tree.get_children())
        tk.title(f'{bot.name} at {time.strftime("%m-%d %H:%M:%S",time.localtime(bot.last_loop_time))}')
        self.courses_display={}

        for course in courses:
            selectable=course['elected_cnt']<course['volume_cnt']
            left=f'{course["volume_cnt"]-course["elected_cnt"]} left'

            in_wishlist=(course['name'],course['classid']) in self.wishlist
            if self.auto_on and not in_wishlist:
                continue

            cid=self.tree.insert(
                '','end',
                text=f'{course["name"]} {course["classid"]}',
                values=(
                    course['teacher'],
                    course['volume_cnt'],
                    course['elected_cnt'],
                    f'{left if selectable else ""}{" ☆" if in_wishlist else ""}'
                )
            )
            self.courses_display[cid]=(bot,course)

orchestrator=Orchestrator()
mainloop()
