from tkinter import *
from tkinter.ttk import *

import os

import captcha
from PIL import Image, ImageTk

from watchdog.observers import Observer
from watchdog.events import PatternMatchingEventHandler

DROPPER_PATH = 'aux_captcha_dropper'

if not os.path.exists(DROPPER_PATH):
    os.mkdir(DROPPER_PATH)

tk=Tk()

msg_var=StringVar(value='将图片拖入文件夹')

tk.title('Captcha Widget')
tk.geometry('%dx%d'%(130+10, 52*4+40))
tk.resizable(False, False)
tk.wm_attributes('-toolwindow',True)
tk.wm_attributes('-topmost',True)

label=Label(tk)
label.pack()

Label(textvariable=msg_var, font='Consolas -25').pack()

def on_created_file(e):
    im = Image.open(e.src_path)
    
    keyfs = captcha.auxview(im)
    
    cvs = Image.new('RGB', (130, 52*4))
    for i, frameim in enumerate(keyfs):
        cvs.paste(frameim, (0, i*52))
        
    label._image = ImageTk.PhotoImage(cvs)
    label['image'] = label._image
    
    res = captcha.recognize(im)
    
    tk.clipboard_clear()
    tk.clipboard_append(res)
    msg_var.set(res.upper())
    
    im.close()
    os.remove(e.src_path)

handler = PatternMatchingEventHandler(['*.gif'], ignore_directories=True, case_sensitive=False)
handler.on_created = on_created_file

observer = Observer()
observer.schedule(handler, DROPPER_PATH, recursive=False)
observer.start()

mainloop()

observer.stop()
observer.join()