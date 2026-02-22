import migen
import os
import shutil
from amaranth import Module as AmModule, Signal as AmSignal, Elaboratable, Cat as AmCat, ClockSignal, ResetSignal
from amaranth.back import verilog
# LiteX/Migen imports
from litex.gen import *
from litex.soc.interconnect.csr import *
from litex.soc.interconnect.csr_eventmanager import EventManager, EventSourceProcess
from litex_boards.targets import sipeed_tang_nano_20k
from litex.soc.integration.builder import Builder

# --- Amaranth UART Core Logic ---

class UART_tx(Elaboratable):
    def __init__(self):
        self.divisor_reg = AmSignal(16)
        self.tx_req = AmSignal()
        self.tx_buff = AmSignal(8)
        self.tx_rdy = AmSignal() 
        self.tx = AmSignal()

    def elaborate(self, platform):
        m = AmModule()
        tx_data = AmSignal(8)
        parity = AmSignal()
        tx_data_counter = AmSignal(4)
        tx_clk_counter = AmSignal(16)
        
        with m.If(tx_clk_counter + 1 == self.divisor_reg):
            m.d.sync += tx_clk_counter.eq(0)
        with m.Else():
            m.d.sync += tx_clk_counter.eq(tx_clk_counter + 1)
        
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
                        tx_data.eq(tx_data >> 1),
                        tx_data_counter.eq(tx_data_counter + 1)
                    ]
                with m.If(tx_data_counter[3]):
                    m.next = "PARITY"
            with m.State("PARITY"):
                with m.If(tx_clk_counter == 0):
                    m.d.sync += self.tx.eq(parity)
                    m.next = "STOP"
            with m.State("STOP"):
                m.d.comb += self.tx_rdy.eq(0)
                with m.If(tx_clk_counter == 0):
                    m.d.sync += [
                        self.tx.eq(1),
                        tx_data_counter.eq(0)
                    ]
                    m.next = "WAIT"
        return m

class UART_rx(Elaboratable):
    def __init__(self):
        self.divisor_reg = AmSignal(16)
        self.rx_rdy = AmSignal()
        self.rx_buff = AmSignal(8)
        self.rx_error = AmSignal()
        self.rx = AmSignal()
    
    def elaborate(self, platform):
        m = AmModule()
        rx_clk_counter = AmSignal(12)
        rx_data_counter = AmSignal(4)
        rx_oversample_counter = AmSignal(4)
        rx_data = AmSignal(8)
        rx_sync = AmSignal(3)
        
        with m.If(rx_clk_counter + 1 == self.divisor_reg >> 4):
            m.d.sync += rx_clk_counter.eq(0)
        with m.Else():
            m.d.sync += rx_clk_counter.eq(rx_clk_counter + 1)
            
        with m.FSM(name='rx_FSM'):
            with m.State("WAIT"):
                m.d.sync += self.rx_rdy.eq(0)
                with m.If(~self.rx & (rx_clk_counter > 0)):
                    m.d.sync += [
                        rx_sync.eq(self.rx),
                        rx_clk_counter.eq(0)
                    ]
                    m.next = "START"
            with m.State("START"):
                with m.If(rx_clk_counter == 0):
                    with m.If(rx_oversample_counter == 7):
                        m.d.sync += [rx_sync[0].eq(self.rx), rx_oversample_counter.eq(rx_oversample_counter + 1)]
                    with m.Elif(rx_oversample_counter == 8):
                        m.d.sync += [rx_sync[1].eq(self.rx), rx_oversample_counter.eq(rx_oversample_counter + 1)]
                    with m.Elif(rx_oversample_counter == 9):
                        m.d.sync += [rx_sync[2].eq(self.rx), rx_oversample_counter.eq(rx_oversample_counter + 1)]
                    with m.Elif(rx_oversample_counter == 15):
                        with m.If(((rx_sync[0] & rx_sync[1]) | (rx_sync[1] & rx_sync[2]) | (rx_sync[0] & rx_sync[2])) == 0):
                            m.next = "DATA"
                            m.d.sync += rx_oversample_counter.eq(0)
                        with m.Else():
                            m.next = "WAIT"
                    with m.Else():
                        m.d.sync += rx_oversample_counter.eq(rx_oversample_counter + 1)
            with m.State("DATA"):
                with m.If(rx_clk_counter == 0):
                    with m.If(rx_data_counter == 8):
                        m.next = "PARITY"
                    with m.Elif(rx_oversample_counter == 7):
                        m.d.sync += [rx_sync[0].eq(self.rx), rx_oversample_counter.eq(rx_oversample_counter + 1)]
                    with m.Elif(rx_oversample_counter == 8):
                        m.d.sync += [rx_sync[1].eq(self.rx), rx_oversample_counter.eq(rx_oversample_counter + 1)]
                    with m.Elif(rx_oversample_counter == 9):
                        m.d.sync += [rx_sync[2].eq(self.rx), rx_oversample_counter.eq(rx_oversample_counter + 1)]
                    with m.Elif(rx_oversample_counter == 15):
                        maj = (rx_sync[0] & rx_sync[1]) | (rx_sync[1] & rx_sync[2]) | (rx_sync[0] & rx_sync[2])
                        m.d.sync += [
                            rx_data.eq(AmCat(rx_data[1:8], maj)),
                            rx_data_counter.eq(rx_data_counter + 1),
                            rx_oversample_counter.eq(rx_oversample_counter + 1)
                        ]
                    with m.Else():
                        m.d.sync += rx_oversample_counter.eq(rx_oversample_counter + 1)
            with m.State("PARITY"):
                with m.If(rx_clk_counter == 0):
                    with m.If(rx_oversample_counter == 7):
                        m.d.sync += [rx_sync[0].eq(self.rx), rx_oversample_counter.eq(rx_oversample_counter + 1)]
                    with m.Elif(rx_oversample_counter == 8):
                        m.d.sync += [rx_sync[1].eq(self.rx), rx_oversample_counter.eq(rx_oversample_counter + 1)]
                    with m.Elif(rx_oversample_counter == 9):
                        m.d.sync += [rx_sync[2].eq(self.rx), rx_oversample_counter.eq(rx_oversample_counter + 1)]
                    with m.Elif(rx_oversample_counter == 15):
                        maj_parity = (rx_sync[0] & rx_sync[1]) | (rx_sync[1] & rx_sync[2]) | (rx_sync[0] & rx_sync[2])
                        m.d.sync += [
                            self.rx_error.eq(rx_data.xor() ^ maj_parity),
                            self.rx_buff.eq(rx_data),
                            rx_oversample_counter.eq(0)
                        ]
                        m.next = "STOP"
                    with m.Else():
                        m.d.sync += rx_oversample_counter.eq(rx_oversample_counter + 1)
            with m.State("STOP"):
                with m.If(rx_clk_counter == 0):
                    with m.If(rx_oversample_counter == 7):
                        m.d.sync += [rx_sync[0].eq(self.rx), rx_oversample_counter.eq(rx_oversample_counter + 1)]
                    with m.Elif(rx_oversample_counter == 8):
                        m.d.sync += [rx_sync[1].eq(self.rx), rx_oversample_counter.eq(rx_oversample_counter + 1)]
                    with m.Elif(rx_oversample_counter == 9):
                        m.d.sync += [rx_sync[2].eq(self.rx), rx_oversample_counter.eq(rx_oversample_counter + 1)]
                    with m.Elif(rx_oversample_counter == 15):
                        maj_stop = (rx_sync[0] & rx_sync[1]) | (rx_sync[1] & rx_sync[2]) | (rx_sync[0] & rx_sync[2])
                        m.d.sync += [
                            self.rx_error.eq(~(maj_stop == 1) | self.rx_error),
                            self.rx_rdy.eq(1),
                            rx_data_counter.eq(0),
                            rx_oversample_counter.eq(0)
                        ]
                        m.next = "WAIT"
                    with m.Else():
                        m.d.sync += rx_oversample_counter.eq(rx_oversample_counter + 1)
        return m

class AmaranthUARTCore(Elaboratable):
    def __init__(self):
        self.divisor_reg = AmSignal(16)
        self.tx_req = AmSignal()
        self.tx_buff = AmSignal(8)
        self.tx_rdy = AmSignal()
        self.tx = AmSignal()
        self.rx_rdy = AmSignal()
        self.rx_buff = AmSignal(8)
        self.rx_error = AmSignal()
        self.rx = AmSignal()

    def elaborate(self, platform):
        m = AmModule()
        m.submodules.tx = tx = UART_tx()
        m.submodules.rx = rx = UART_rx()
        m.d.comb += [
            tx.divisor_reg.eq(self.divisor_reg),
            rx.divisor_reg.eq(self.divisor_reg),
            tx.tx_req.eq(self.tx_req),
            tx.tx_buff.eq(self.tx_buff),
            self.tx_rdy.eq(tx.tx_rdy),
            self.tx.eq(tx.tx),
            self.rx_rdy.eq(rx.rx_rdy),
            self.rx_buff.eq(rx.rx_buff),
            self.rx_error.eq(rx.rx_error),
            rx.rx.eq(self.rx)
        ]
        return m

# --- Migen/LiteX Wrapper ---
class UART_Custom(migen.Module, AutoCSR):
    def __init__(self):
        # 1. LiteX BIOS expects 'rxtx' to be both readable and writable.
        # CSR(8) creates a register where CPU writes go to `.storage`,
        # and CPU reads are supplied by the `.w` attribute.
        self.rxtx = CSR(8)
        
        # 2. BIOS expects exactly 'txfull' and 'rxempty' as distinct CSR registers, 
        # not as fields inside a 'status' register.
        self.txfull = CSRStatus(1)
        self.rxempty = CSRStatus(1)
        
        # 3. BIOS expects event sources named exactly 'rx' and 'tx'.
        self.submodules.ev = EventManager()
        self.ev.rx = EventSourceProcess(edge="rising")
        self.ev.tx = EventSourceProcess(edge="rising")
        self.ev.finalize() # CRUCIAL: This generates the pending/enable registers!

        self.divisor = CSRStorage(16, reset=234) # 27MHz / 115200

        self.tx = migen.Signal()
        self.rx = migen.Signal()
        
        tx_rdy_sig = migen.Signal()
        rx_rdy_sig = migen.Signal()
        rx_data_sig = migen.Signal(8)

        # Connect to Amaranth Core
        self.specials += migen.Instance("AmaranthUARTCore",
            i_clk           = migen.ClockSignal("sys"),
            i_rst           = migen.ResetSignal("sys"),
            i_divisor_reg   = self.divisor.storage,
            i_tx_req        = self.rxtx.re,       # Pulse on CPU write
            i_tx_buff       = self.rxtx.r,        # Data written by the CPU
            o_tx_rdy        = tx_rdy_sig,
            o_tx            = self.tx,
            i_rx            = self.rx,
            o_rx_rdy        = rx_rdy_sig,
            o_rx_buff       = rx_data_sig,        # Pipe RX data out
            o_rx_error      = migen.Signal()
        )
        
        self.comb += [
            self.rxtx.w.eq(rx_data_sig),          # Map RX data to the CPU read port
            self.txfull.status.eq(~tx_rdy_sig),
            self.rxempty.status.eq(~rx_rdy_sig),
            self.ev.rx.trigger.eq(rx_rdy_sig),
            self.ev.tx.trigger.eq(tx_rdy_sig),
        ]
               
class SoC_Custom(sipeed_tang_nano_20k.BaseSoC):
    def __init__(self, **kwargs):
        kwargs["integrated_rom_size"]  = 0x8000
        kwargs["integrated_sram_size"] = 0x4000
        kwargs["with_uart"] = False 
        super().__init__(**kwargs)
        
        # ... (Amaranth generation code stays the same) ...

        # Request pins
        serial_pads = self.platform.request("serial")
        
        # Add UART
        # Note: We don't pass platform here as it wasn't used in __init__
        self.submodules.uart = UART_Custom() 
        self.add_csr("uart")
        self.add_interrupt("uart")
        
        self.comb += [
            serial_pads.tx.eq(self.uart.tx),
            self.uart.rx.eq(serial_pads.rx)
        ]

if __name__ == "__main__":
    soc = SoC_Custom(cpu_type="vexriscv")
    # Change compile_software to False
    builder = Builder(soc) 
    builder.build(run=False)