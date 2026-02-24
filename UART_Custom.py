from litex.soc.interconnect.csr_eventmanager import EventManager, EventSourceProcess
from UART_mod import *
from amaranth.back import verilog as am_verilog
import migen as mg
from litex.soc.interconnect.csr import AutoCSR, CSRStorage, CSRStatus

class UART_Custom(mg.Module, AutoCSR):
    def __init__(self, platform, pads):
        self.platform = platform
        
        self.rxtx    = CSRStorage(8)
        self.rx_data = CSRStatus(8)
        self.txfull  = CSRStatus()
        self.rxempty = CSRStatus()
        self.divisor = CSRStorage(16, reset=234)

        self.submodules.ev = EventManager()
        self.ev.tx = EventSourceProcess()
        self.ev.rx = EventSourceProcess()
        self.ev.finalize()
        
        tx_rdy_bridge = mg.Signal()
        rx_rdy_bridge = mg.Signal()
        rx_byte_bridge = mg.Signal(8)
        rx_pending = mg.Signal()
        rx_buffer  = mg.Signal(8)

        tx_logic = UART_tx()
        rx_logic = UART_rx()
        
        v_tx = am_verilog.convert(tx_logic, name="uart_tx", ports=[
            tx_logic.divisor_reg, tx_logic.tx_buff, tx_logic.tx_req, 
            tx_logic.tx, tx_logic.tx_rdy
        ])
        v_rx = am_verilog.convert(rx_logic, name="uart_rx", ports=[
            rx_logic.divisor_reg, rx_logic.rx, rx_logic.rx_buff, 
            rx_logic.rx_rdy
        ])

        self.specials += mg.Instance("uart_tx",
            i_clk         = mg.ClockSignal(),
            i_rst         = mg.ResetSignal(),
            i_divisor_reg = self.divisor.storage,
            i_tx_buff     = self.rxtx.storage,
            i_tx_req      = self.rxtx.re,
            o_tx          = pads.tx,
            o_tx_rdy      = tx_rdy_bridge
        )

        self.specials += mg.Instance("uart_rx",
            i_clk         = mg.ClockSignal(),
            i_rst         = mg.ResetSignal(),
            i_divisor_reg = self.divisor.storage,
            i_rx          = pads.rx,
            o_rx_buff     = rx_byte_bridge,
            o_rx_rdy      = rx_rdy_bridge
        )

        self.sync += [
            mg.If(rx_rdy_bridge,
                rx_pending.eq(1),
                rx_buffer.eq(rx_byte_bridge)
            ),
            mg.If(self.rxtx.re,
                rx_pending.eq(0)
            )
        ]

        self.comb += [
            self.txfull.status.eq(~tx_rdy_bridge),
            self.rxempty.status.eq(~rx_pending),
            self.rx_data.status.eq(rx_buffer)
        ]

        self._verilog_tx = v_tx
        self._verilog_rx = v_rx

    def do_finalize(self):
        import os
        gen_dir = os.path.join(self.platform.output_dir, "gateware")
        os.makedirs(gen_dir, exist_ok=True)
        tx_path = os.path.join(gen_dir, "uart_tx.v")
        rx_path = os.path.join(gen_dir, "uart_rx.v")
        with open(tx_path, "w") as f: f.write(self._verilog_tx)
        with open(rx_path, "w") as f: f.write(self._verilog_rx)
        self.platform.add_source(tx_path)
        self.platform.add_source(rx_path)
        
        
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


# class SoC_Custom(sipeed_tang_nano_20k.BaseSoC):
#     def __init__(self, **kwargs):
#         sipeed_tang_nano_20k.BaseSoC.__init__(self, **kwargs)
        
#         self.platform = sipeed_tang_nano_20k.Platform()
        
#         serial_pads = self.platform.request("serial")

#         self.submodules.my_uart = UART_Custom(self.platform)
#         self.add_csr("uart_custom")
#         self.add_interrupt("uart_custom")

#         self.comb += [
#             serial_pads.tx.eq(self.my_uart.tx),
#             self.my_uart.rx.eq(serial_pads.rx)
#         ]