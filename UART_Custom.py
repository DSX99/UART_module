from amaranth import *
from amaranth.sim import Simulator
import random
from litex.soc.interconnect.csr import *
from amaranth import Module as AmaranthModule
from litex.gen import *
from litex.soc.interconnect.csr_eventmanager import EventManager, EventSourceProcess
from litex_boards.targets import sipeed_tang_nano_20k
from litex.soc.integration.soc_core import SoCCore
from litex.soc.integration.builder import Builder

class UART_tx(Elaboratable):
    def __init__(self):
        self.divisor_reg = Signal(16)
        
        self.tx_req = Signal()
        self.tx_buff = Signal(8)
        self.tx_rdy = Signal() 
        self.tx = Signal()

    def elaborate(self,platform):
        m = Module()
        
        tx_data = Signal(8)
        parity = Signal()
        tx_data_counter = Signal(4)
        tx_clk_counter = Signal(16)
        
        with m.If(tx_clk_counter+1 == self.divisor_reg):
            m.d.sync += tx_clk_counter.eq(0)
        with m.Else():
            m.d.sync += tx_clk_counter.eq(tx_clk_counter+1)
        
        with m.FSM(name='tx_FSM'):
            with m.State("WAIT"):
                m.d.sync += self.tx.eq(1)
                m.d.comb += self.tx_rdy.eq(1)
                
                with m.If(self.tx_req):
                    m.d.comb += self.tx_rdy.eq(0)
                    m.d.sync += [
                        self.tx.eq(0),
                        tx_data.eq(self.tx_buff),
                        parity.eq(self.tx_buff.xor()),
                        tx_clk_counter.eq(1)
                    ]
                    m.next = "DATA"
            with m.State("DATA"):
                m.d.comb += self.tx_rdy.eq(0)
                
                with m.If(tx_clk_counter == 0):
                    m.d.sync += [
                        self.tx.eq(tx_data[0]),
                        tx_data.eq(tx_data>>1),
                        tx_data_counter.eq(tx_data_counter+1)
                    ]
                    
                with m.If(tx_data_counter[3]):
                    m.next ="PARITY"
            with m.State("PARITY"):
                with m.If(tx_clk_counter == 0):
                    m.d.sync += self.tx.eq(parity)
                    m.next="STOP"
            with m.State("STOP"):
                m.d.comb += self.tx_rdy.eq(0)
                
                with m.If(tx_clk_counter == 0):
                    m.d.sync += [
                        self.tx.eq(1),
                        tx_data_counter.eq(0)
                    ]
                    m.next="WAIT"
        
        return m

class UART_rx(Elaboratable):
    def __init__(self):
        self.divisor_reg = Signal(16)
        
        self.rx_rdy = Signal()
        self.rx_buff = Signal(8)
        self.rx_error = Signal()
        self.rx = Signal()
    
    def elaborate(self,platform):
        m = Module()
        
        #RX
        #clk_counter assumes 16x oversampling, so needs only 12 bits
        rx_clk_counter = Signal(12)
        rx_data_counter = Signal(4)
        rx_oversample_counter = Signal(4)
        rx_data = Signal(8)
        rx_sync = Signal(3)
        
        with m.If(rx_clk_counter+1 == self.divisor_reg>>4):
            m.d.sync += rx_clk_counter.eq(0)
        with m.Else():
            m.d.sync += rx_clk_counter.eq(rx_clk_counter+1)
            
        with m.FSM(name='rx_FSM'):
            with m.State("WAIT"):
                m.d.sync += [
                    self.rx_rdy.eq(0)
                ]
                with m.If(~self.rx & rx_clk_counter):
                    m.d.sync += [
                        rx_sync.eq(self.rx),
                        rx_clk_counter.eq(0)
                    ]
                    m.next="START"
            with m.State("START"):
                with m.If(rx_clk_counter == 0):
                    with m.If(rx_oversample_counter == 7):
                        m.d.sync += [
                            rx_sync[0].eq(self.rx),
                            rx_oversample_counter.eq(rx_oversample_counter+1)
                        ]
                    with m.Elif(rx_oversample_counter == 8):
                        m.d.sync += [
                            rx_sync[1].eq(self.rx),
                            rx_oversample_counter.eq(rx_oversample_counter+1)
                        ]
                    with m.Elif(rx_oversample_counter == 9):
                        m.d.sync += [
                            rx_sync[2].eq(self.rx),
                            rx_oversample_counter.eq(rx_oversample_counter+1)
                        ]
                    with m.Elif(rx_oversample_counter == 15):
                        with m.If(((rx_sync[0]&rx_sync[1])|(rx_sync[1]&rx_sync[2])|(rx_sync[0]&rx_sync[2])) == 0):
                            m.next=("DATA")
                            m.d.sync += rx_oversample_counter.eq(0)
                        with m.Else():
                            m.next=("WAIT")
                    with m.Else():
                        m.d.sync += rx_oversample_counter.eq(rx_oversample_counter+1)
            with m.State("DATA"):
                with m.If(rx_clk_counter == 0):
                    with m.If(rx_data_counter==8):
                        m.next=("PARITY")
                    with m.Elif(rx_oversample_counter == 7):
                        m.d.sync += [
                            rx_sync[0].eq(self.rx),
                            rx_oversample_counter.eq(rx_oversample_counter+1)
                        ]
                    with m.Elif(rx_oversample_counter == 8):
                        m.d.sync += [
                            rx_sync[1].eq(self.rx),
                            rx_oversample_counter.eq(rx_oversample_counter+1)
                        ]
                    with m.Elif(rx_oversample_counter == 9):
                        m.d.sync += [
                            rx_sync[2].eq(self.rx),
                            rx_oversample_counter.eq(rx_oversample_counter+1)
                        ]
                    with m.Elif(rx_oversample_counter == 15):
                        m.d.sync += [
                            rx_data.eq(Cat(rx_data[1:8],(rx_sync[0]&rx_sync[1])|(rx_sync[1]&rx_sync[2])|(rx_sync[0]&rx_sync[2]))),
                            rx_data_counter.eq(rx_data_counter+1),
                            rx_oversample_counter.eq(rx_oversample_counter+1)
                        ]
                    with m.Else():
                        m.d.sync += rx_oversample_counter.eq(rx_oversample_counter+1)
            with m.State("PARITY"):
                with m.If(rx_clk_counter == 0):
                    with m.If(rx_oversample_counter == 7):
                        m.d.sync += [
                            rx_sync[0].eq(self.rx),
                            rx_oversample_counter.eq(rx_oversample_counter+1)
                        ]
                    with m.Elif(rx_oversample_counter == 8):
                        m.d.sync += [
                            rx_sync[1].eq(self.rx),
                            rx_oversample_counter.eq(rx_oversample_counter+1)
                        ]
                    with m.Elif(rx_oversample_counter == 9):
                        m.d.sync += [
                            rx_sync[2].eq(self.rx),
                            rx_oversample_counter.eq(rx_oversample_counter+1)
                        ]
                    with m.Elif(rx_oversample_counter == 15):
                        parity = (rx_sync[0]&rx_sync[1])|(rx_sync[1]&rx_sync[2])|(rx_sync[0]&rx_sync[2])
                        m.d.sync += [
                            self.rx_error.eq(rx_data.xor() ^ parity),
                            self.rx_buff.eq(rx_data),
                            rx_oversample_counter.eq(0)
                        ]
                        m.next=("STOP")
                    with m.Else():
                        m.d.sync += rx_oversample_counter.eq(rx_oversample_counter+1)
            with m.State("STOP"):
                with m.If(rx_clk_counter == 0):
                    with m.If(rx_oversample_counter == 7):
                        m.d.sync += [
                            rx_sync[0].eq(self.rx),
                            rx_oversample_counter.eq(rx_oversample_counter+1)
                        ]
                    with m.Elif(rx_oversample_counter == 8):
                        m.d.sync += [
                            rx_sync[1].eq(self.rx),
                            rx_oversample_counter.eq(rx_oversample_counter+1)
                        ]
                    with m.Elif(rx_oversample_counter == 9):
                        m.d.sync += [
                            rx_sync[2].eq(self.rx),
                            rx_oversample_counter.eq(rx_oversample_counter+1)
                        ]
                    with m.Elif(rx_oversample_counter == 15):
                        m.d.sync += [
                            self.rx_error.eq(~(((rx_sync[0]&rx_sync[1])|(rx_sync[1]&rx_sync[2])|(rx_sync[0]&rx_sync[2]))==1)|self.rx_error),
                            self.rx_rdy.eq(1),
                            rx_data_counter.eq(0),
                            rx_oversample_counter.eq(0)
                        ]
                        m.next=("WAIT")
                    with m.Else():
                        m.d.sync += rx_oversample_counter.eq(rx_oversample_counter+1)
        return m

class UART_Custom(Module, AutoCSR):
    def __init__(self):
        self.divisor = CSRStorage(16)
        self.tx_data = CSRStorage(8)
        self.tx_req = CSRStorage(1)
        self.status = CSRStatus(fields=[
            CSRField("tx_rdy", offset=0, description="TX is ready"),
            CSRField("rx_rdy", offset=1, description="RX has data available"),
            CSRField("rx_err", offset=2, description="RX Error flag"),
        ])
        self.rx_data = CSRStatus(8)

        self.submodules.tx = tx = UART_tx()
        self.submodules.rx = rx = UART_rx()

        self.submodules.ev = EventManager()
        self.ev.rx_done = EventSourceProcess()
        
        self.comb += [
            tx.divisor_reg.eq(self.divisor.storage),
            rx.divisor_reg.eq(self.divisor.storage),
            
            tx.tx_buff.eq(self.tx_data.storage),
            tx.tx_req.eq(self.tx_req.re),

            self.rx_data.status.eq(rx.rx_buff),

            self.status.fields.tx_rdy.eq(tx.tx_rdy),
            self.status.fields.rx_rdy.eq(rx.rx_rdy),
            self.status.fields.rx_err.eq(rx.rx_error),
                    
            self.ev.rx_done.trigger.eq(self.rx.rx_rdy)
        ]
        
        self.tx = tx.tx
        self.rx = rx.rx

#tb send value on tx, expect same on rx

# class UART_Loopback_Test(Elaboratable):
#     def __init__(self):
#         self.tx_buff = Signal(8)
#         self.tx_req  = Signal()
#         self.tx_rdy  = Signal()
        
#         self.rx_buff = Signal(8)
#         self.rx_rdy  = Signal()
#         self.rx_error= Signal()

#     def elaborate(self, platform):
#         m = Module()
        
#         m.submodules.tx = tx = UART_tx()
#         m.submodules.rx = rx = UART_rx()

#         m.d.comb += rx.rx.eq(tx.tx)
        
#         m.d.comb += [
#             rx.divisor_reg.eq(32),
#             tx.divisor_reg.eq(32)
#         ]

#         m.d.comb += [
#             tx.tx_buff.eq(self.tx_buff),
#             tx.tx_req.eq(self.tx_req),
#             self.tx_rdy.eq(tx.tx_rdy),
            
#             self.rx_buff.eq(rx.rx_buff),
#             self.rx_rdy.eq(rx.rx_rdy),
#             self.rx_error.eq(rx.rx_error)
#         ]
        
#         return m

# async def testbench(ctx):
#     for _ in range(10):
#         await ctx.tick()
#     check=0
#     for i in range(1, 101):
#         while not ctx.get(dut.tx_rdy):
#             await ctx.tick()

#         send_val = random.randint(0, 255)
#         print(f"sent {bin(send_val)}")
        
#         ctx.set(dut.tx_buff, send_val)
#         ctx.set(dut.tx_req, 1)
#         await ctx.tick()
#         ctx.set(dut.tx_req, 0)

#         count=0
#         while not ctx.get(dut.rx_rdy):
#             await ctx.tick()
#             if(count>1000):
#                 print("too much time on rx")
#                 return
#             count+=1

#         received_val = ctx.get(dut.rx_buff)
#         error = ctx.get(dut.rx_error)
        
#         if received_val == send_val and not error:
#             print("got right value on rx")
#         else:
#             print(f"error with data {bin(received_val)} and error {bin(error)}")
#             check+=1

#         for _ in range(50):
#             await ctx.tick()
#     if(check):
#         print("Error")
#     else:
#         print("All good")

#tb send on rx, expect reversed on tx, interface to talk through is rx2 and tx2

# class UART_Loopback_Test(Elaboratable):
#     def __init__(self):
#         self.tx_buff = Signal(8)
#         self.tx_req  = Signal()
#         self.tx_rdy  = Signal()
        
#         self.rx_buff = Signal(8)
#         self.rx_rdy  = Signal()
#         self.rx_error= Signal()
        
#     def elaborate(self, platform):
#         m = Module()
        
#         m.submodules.tx = tx = UART_tx()
#         m.submodules.rx = rx = UART_rx()
        
#         m.submodules.tx2 = tx2 = UART_tx()
#         m.submodules.rx2 = rx2 = UART_rx()

#         m.d.comb += [
#             tx.tx_buff.eq(rx.rx_buff[::-1]),
#             tx.tx_req.eq(rx.rx_rdy)
#         ]
        
#         m.d.comb += [
#             rx.rx.eq(tx2.tx),
#             rx2.rx.eq(tx.tx)
#         ]

#         m.d.comb += [
#             rx.divisor_reg.eq(32),
#             tx.divisor_reg.eq(32),
#             rx2.divisor_reg.eq(32),
#             tx2.divisor_reg.eq(32)
#         ]

#         m.d.comb += [
#             tx2.tx_buff.eq(self.tx_buff),
#             tx2.tx_req.eq(self.tx_req),
#             self.tx_rdy.eq(tx2.tx_rdy),
            
#             self.rx_buff.eq(rx2.rx_buff),
#             self.rx_rdy.eq(rx2.rx_rdy),
#             self.rx_error.eq(rx2.rx_error)
#         ]
        
#         return m

# async def testbench(ctx):
#     for _ in range(10):
#         await ctx.tick()
#     check=0
#     for i in range(1, 101):
#         while not ctx.get(dut.tx_rdy):
#             await ctx.tick()

#         send_val = random.randint(0, 255)
#         #print(f"sent {bin(send_val)}")
        
#         ctx.set(dut.tx_buff, send_val)
#         ctx.set(dut.tx_req, 1)
#         await ctx.tick()
#         ctx.set(dut.tx_req, 0)

#         count=0
#         while not ctx.get(dut.rx_rdy):
#             await ctx.tick()
#             if(count>1000):
#                 print("too much time on rx")
#                 return
#             count+=1

#         received_val = ctx.get(dut.rx_buff)
#         error = ctx.get(dut.rx_error)
    
#         if bin(send_val)[2:].zfill(8) == (bin(received_val)[2:].zfill(8))[::-1] and not error:
#             print("got right value on rx")
#         else:
#             print(f"error with data {bin(received_val)} and error {bin(error)}")
#             check+=1

#         for _ in range(50):
#             await ctx.tick()
#     if(check):
#         print("Error")
#     else:
#         print("All good")


# if __name__ == "__main__":
#     dut = UART_Loopback_Test() 
#     sim = Simulator(dut)
#     sim.add_clock(1e-8) 
#     sim.add_testbench(testbench)
    
#     with sim.write_vcd("test.vcd"):
#         sim.run()


class SoC_Custom(sipeed_tang_nano_20k.BaseSoC):
    def __init__(self, **kwargs):
        sipeed_tang_nano_20k.BaseSoC.__init__(self, **kwargs)

        serial_pads = self.platform.request("uart")

        self.submodules.my_uart = UART_Custom(self.platform)
        self.add_csr("my_uart")
        self.add_interrupt("my_uart")

        self.comb += [
            serial_pads.tx.eq(self.my_uart.tx),
            self.my_uart.rx.eq(serial_pads.rx)
        ]

# 5. Build it!
soc = SoC_Custom(cpu_type="vexriscv")
builder = Builder(soc, output_dir="build", compile_software=True)
builder.build()