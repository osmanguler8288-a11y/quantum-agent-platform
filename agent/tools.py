class EqV2Tool:
    def __init__(self, client):
        self.client = client

    def run(self, input_data: dict):
        return self.client.call(
            tool_name="eqv2_optimize",
            params=input_data
        )