import collections
import queue
import threading
import time

# to trigger logging window update; None for list itself (e.g. status update)
log_q=queue.Queue()

class Logger:
    MAX_LOG=200
    VERBOSE=False # class attribute so shared across instances

    def __init__(self,name):
        self.logs=collections.deque()
        self.name=name
        self.lid_begin=0
        self.lid_end=0
        self.lock=threading.Lock()
        self('info', 'HEED by @xmcp')

    def __call__(self,typ,msg):
        if not self.VERBOSE and typ=='debug':
            return
        with self.lock:
            if len(self.logs)>=self.MAX_LOG:
                self.logs.popleft()
                self.lid_begin+=1
            self.logs.append((time.time(),typ,msg))
            log_q.put(self.name)
            self.lid_end+=1
