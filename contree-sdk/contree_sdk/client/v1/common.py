# from contree_sdk.client.v1.files import FilesMixin
from contree_sdk.client.v1.images import ImagesMixin
from contree_sdk.client.v1.inspect import InspectMixin

# from contree_sdk.client.v1.instances import InstancesMixin
# from contree_sdk.client.v1.operations import OperationsMixin


# todo add proper paths
class V1Mixin(
    ImagesMixin,
    # FilesMixin,
    # InstancesMixin,
    # OperationsMixin,
    InspectMixin,
):
    pass
