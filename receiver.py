import socket
import select
import queue
import asyncio
import random
import time
from utils import Logger, Constant, PACK, Field


class Reciever:
    def __init__(self, addr, port, remotePath, localPath, throw_rate=0):
        self.sender_addr = addr
        self.port = port
        self.f = open(localPath, 'wb')
        self.remotePath = remotePath
        self.buffer = queue.deque()
        self.ws = 20
        self.done = False
        self.logger = Logger('Receiver {}/Sender {}:{}'.format(port, *addr))
        self.throw_rate = throw_rate

    def run(self):
        actors = queue.deque([self.recv(), self.handleData()])
        while actors:
            task = actors.popleft()
            try:
                next(task)
                actors.append(task)
            except StopIteration:
                pass
        self.logger.log('Task Done')

    def recv(self):
        ACK = 0
        sc = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sc.bind(('', self.port))
        kw = {Field.FILE_NAME: self.remotePath, Field.ACK: ACK,
              Field.RWND: self.ws, Field.PORT: self.port}
        while True:
            empty = PACK.serialize(b'', kw)

            self.logger.log('Sending ACK: {}'.format(kw[Field.ACK]))
            sc.sendto(empty, self.sender_addr)
            seq = sc.recv(Constant.MSS + Field.HEADER_LEN)
            rkw, data = PACK.deserialize(seq)

            if len(self.buffer) < self.ws and random.random() >= self.throw_rate:   # 随机丢包
                self.logger.log('receive SEQ: {} expected SEQ: {}'.format(
                    rkw[Field.SEQ], ACK + 1))
                if rkw[Field.SEQ] == ACK + 1:
                    ACK += 1
                    self.buffer.append(data)
                    self.logger.log('Correct SEQ: {}'.format(ACK))
                    if ACK == rkw[Field.SEQ_NUM] - 1:
                        self.done = True
                    elif ACK == rkw[Field.SEQ_NUM]:
                        break
                else:
                    self.logger.log('Unexpected SEQ {}'.format(rkw[Field.SEQ]))
                kw[Field.ACK] = rkw[Field.SEQ]
            else:
                self.logger.log('Full Queue')

            if rkw[Field.SEQ] == Field.EMPTY:
                kw[Field.ACK] = Field.EMPTY
            kw[Field.RWND] = self.ws - len(self.buffer)
            yield
        sc.close()

    def handleData(self):
        part = 0
        while not self.f.closed:
            while self.buffer and random.random() > Constant.HANDLE_PRO:
                data = self.buffer.popleft()
                self.f.write(data)
                part += 1
                self.logger.log('Writing {} to file'.format(part))
            if self.done and not self.buffer:
                self.f.close()
                self.logger.log('Receive file done')
            yield

