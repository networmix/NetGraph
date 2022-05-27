from ngraph.layers import IPConnection, IPDevice, InfraConnection, InfraLocation
from ngraph.network import Net, TrafficClass, TrafficDemand, TrafficDemands


class TestDemands:
    def test_demand_1(self):
        demands = TrafficDemands()
        demands.add_demand(TrafficDemand("dc1-iad", "dc2-iad", TrafficClass.BRONZE, 25))
        demands.add_demand(TrafficDemand("dc1-iad", "dc2-iad", TrafficClass.BRONZE, 35))
        demands.add_demand(TrafficDemand("dc1-iad", "dc2-iad", TrafficClass.ICP, 15))
        # print(demands.demands_ds.df)
        # raise


class TestNetwork:
    def test_init(self):
        Net()

    def test_net_1(self):
        net = Net()
        net.add_nodes_edges(
            nodes=[
                InfraLocation("pdx1", airport_code="pdx"),
                InfraLocation("pdx2", airport_code="pdx"),
                InfraLocation("pdx-dc1", airport_code="pdx"),
                InfraLocation("pdx-dc2", airport_code="pdx"),
                InfraLocation("ord1", airport_code="ord"),
                InfraLocation("ord2", airport_code="ord"),
                InfraLocation("iad1", airport_code="iad"),
                InfraLocation("iad2", airport_code="iad"),
                InfraLocation("iad-dc1", airport_code="iad"),
                InfraLocation("iad-dc2", airport_code="iad"),
                IPDevice("bb01-pdx1", infra_location="pdx1"),
                IPDevice("bb02-pdx1", infra_location="pdx1"),
                IPDevice("bb01-pdx2", infra_location="pdx2"),
                IPDevice("bb02-pdx2", infra_location="pdx2"),
                IPDevice("bb01-iad1", infra_location="iad1"),
                IPDevice("bb02-iad1", infra_location="iad1"),
                IPDevice("bb01-iad2", infra_location="iad2"),
                IPDevice("bb02-iad2", infra_location="iad2"),
                IPDevice("bb01-ord1", infra_location="ord1"),
                IPDevice("bb02-ord1", infra_location="ord1"),
                IPDevice("bb01-ord2", infra_location="ord2"),
                IPDevice("bb02-ord2", infra_location="ord2"),
                IPDevice("dc1-pdx", infra_location="pdx-dc1"),
                IPDevice("dc2-pdx", infra_location="pdx-dc2"),
                IPDevice("dc1-iad", infra_location="iad-dc1"),
                IPDevice("dc2-iad", infra_location="iad-dc2"),
            ],
            edges=[
                InfraConnection("pdx1", "pdx2"),
                InfraConnection("iad1", "iad2"),
                InfraConnection("ord1", "ord2"),
                InfraConnection("ord1", "pdx1"),
                InfraConnection("ord2", "pdx2"),
                InfraConnection("ord1", "iad1"),
                InfraConnection("ord2", "iad2"),
                IPConnection("bb01-pdx1", "bb02-pdx1"),
                IPConnection("bb01-pdx2", "bb02-pdx2"),
                IPConnection("bb01-pdx1", "bb01-pdx2"),
                IPConnection("bb02-pdx1", "bb02-pdx2"),
                IPConnection("bb01-ord1", "bb02-ord1"),
                IPConnection("bb01-ord2", "bb02-ord2"),
                IPConnection("bb01-ord1", "bb01-ord2"),
                IPConnection("bb02-ord1", "bb02-ord2"),
                IPConnection("bb01-iad1", "bb02-iad1"),
                IPConnection("bb01-iad2", "bb02-iad2"),
                IPConnection("bb01-iad1", "bb01-iad2"),
                IPConnection("bb02-iad1", "bb02-iad2"),
                IPConnection("bb01-pdx1", "bb01-ord1"),
                IPConnection("bb01-pdx2", "bb01-ord2"),
                IPConnection("bb02-pdx1", "bb02-ord1"),
                IPConnection("bb02-pdx2", "bb02-ord2"),
                IPConnection("bb01-ord1", "bb01-iad1"),
                IPConnection("bb01-ord2", "bb01-iad2"),
                IPConnection("dc1-pdx", "bb01-pdx1"),
                IPConnection("dc1-pdx", "bb01-pdx2"),
                IPConnection("dc2-pdx", "bb02-pdx1"),
                IPConnection("dc2-pdx", "bb02-pdx2"),
                IPConnection("dc1-iad", "bb01-iad1"),
                IPConnection("dc1-iad", "bb01-iad2"),
                IPConnection("dc2-iad", "bb02-iad1"),
                IPConnection("dc2-iad", "bb02-iad2"),
            ],
        )

        print(
            net.ip_layer.get_max_flows(
                expr="name.str.contains('dc')", source_routing=False
            )
        )
        # print(net.infra_layer.edges_ds.df)
        # print(net.ip_layer.edges_ds.df)

        net.add_traffic_demands(
            [
                TrafficDemand("dc1-iad", "dc2-iad", TrafficClass.BRONZE, 25),
                TrafficDemand("dc1-iad", "dc2-iad", TrafficClass.ICP, 15),
                TrafficDemand("dc2-iad", "dc1-iad", TrafficClass.BRONZE, 45),
                TrafficDemand("dc2-iad", "dc1-iad", TrafficClass.ICP, 25),
            ]
        )
        # net.place_traffic_demands()
        # raise
