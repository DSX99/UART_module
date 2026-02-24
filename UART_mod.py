from amaranth import *

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
                    m.next ="STOP"
            # with m.State("PARITY"):
            #     with m.If(tx_clk_counter == 0):
            #         m.d.sync += self.tx.eq(parity)
            #         m.next="STOP"
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
                        m.next=("STOP")
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
            # with m.State("PARITY"):
            #     with m.If(rx_clk_counter == 0):
            #         with m.If(rx_oversample_counter == 7):
            #             m.d.sync += [
            #                 rx_sync[0].eq(self.rx),
            #                 rx_oversample_counter.eq(rx_oversample_counter+1)
            #             ]
            #         with m.Elif(rx_oversample_counter == 8):
            #             m.d.sync += [
            #                 rx_sync[1].eq(self.rx),
            #                 rx_oversample_counter.eq(rx_oversample_counter+1)
            #             ]
            #         with m.Elif(rx_oversample_counter == 9):
            #             m.d.sync += [
            #                 rx_sync[2].eq(self.rx),
            #                 rx_oversample_counter.eq(rx_oversample_counter+1)
            #             ]
            #         with m.Elif(rx_oversample_counter == 15):
            #             parity = (rx_sync[0]&rx_sync[1])|(rx_sync[1]&rx_sync[2])|(rx_sync[0]&rx_sync[2])
            #             m.d.sync += [
            #                 self.rx_error.eq(rx_data.xor() ^ parity),
            #                 self.rx_buff.eq(rx_data),
            #                 rx_oversample_counter.eq(0)
            #             ]
            #             m.next=("STOP")
            #         with m.Else():
            #             m.d.sync += rx_oversample_counter.eq(rx_oversample_counter+1)
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
