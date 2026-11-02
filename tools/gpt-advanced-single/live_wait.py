"""Adjust a running deadline without reading Tk variables from a worker."""
from threading import Condition
from time import monotonic

class LiveWait:
    def __init__(self,value):
        self.value=value
        self.cv=Condition()

    def set(self,value):
        with self.cv:
            self.value=value
            self.cv.notify_all()

    def run(self,device,status):
        start=monotonic()
        last=None
        with self.cv:
            while True:
                device.check()
                if self.value!=last:
                    last=self.value
                    status(f'等待回答 {last:g} 秒')
                left=start+self.value-monotonic()
                if left<=0:return
                self.cv.wait(min(left,.1))
