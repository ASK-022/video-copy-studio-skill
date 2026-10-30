"""Tk progress view: measured bytes, throughput and explicit source transitions."""
import tkinter as tk
from tkinter import ttk
from contenthub_progress import ProgressState


class ProgressPanel:
    def __init__(self,parent,width=740,offline=False):
        self.state=ProgressState();self.frame=ttk.Frame(parent);self.frame.pack(fill='x',pady=(10,4));self.busy=False;self.running=False;self.offline=offline
        self.variables={name:tk.StringVar() for name in ('phase','file','source','stats','switch','message')}
        for name,prefix,bold in [('phase','',True),('file','当前文件：',False),('source','当前来源：',False),('stats','',False)]:
            label=ttk.Label(self.frame,textvariable=self.variables[name],wraplength=width,font=('Microsoft YaHei UI',10,'bold') if bold else ('Microsoft YaHei UI',9))
            label.pack(anchor='w',fill='x',pady=(0,4))
        self.bar=ttk.Progressbar(self.frame,mode='determinate',maximum=100);self.bar.pack(fill='x',pady=(2,7))
        for name in ('switch','message'):
            ttk.Label(self.frame,textvariable=self.variables[name],wraplength=width,font=('Microsoft YaHei UI',9),foreground='#555555').pack(anchor='w',fill='x',pady=(0,4))
        self.refresh()

    def apply(self,event):self.state.apply(event);self.refresh()

    def set_busy(self,value):self.busy=value;self.refresh()

    def reset(self):self.state=ProgressState();self.refresh()

    def refresh(self):
        value=self.state.display()
        if self.offline:
            if self.state.index==0:value['source']='本机完整离线包'
            value['switch']='完整离线资源，不连接下载源'
            if self.state.message.startswith(('正在连接当前下载源','正在传输')):value['message']='正在本机校验／解压，已完成文件会保留。'
        self.variables['phase'].set(value['phase']);self.variables['file'].set('当前文件：'+value['file'])
        self.variables['source'].set('当前来源：'+value['source'])
        self.variables['stats'].set(value['bytes']+'    速度：'+value['speed']+'    '+value['eta'])
        self.variables['switch'].set(('安装方式：' if self.offline else '线路切换：')+value['switch']);self.variables['message'].set(value['message'])
        if value['percent'] is not None:
            if self.running:self.bar.stop();self.running=False
            self.bar.configure(mode='determinate',value=min(100,value['percent']))
        elif self.busy:
            if not self.running:self.bar.configure(mode='indeterminate');self.bar.start(15);self.running=True
        else:
            self.bar.stop();self.running=False;self.bar.configure(mode='determinate',value=0)
        return value
