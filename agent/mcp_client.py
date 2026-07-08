class MCPClient:
    def call(self,tool_name:str,params:dict):
        print(f"[mcp call] tool = {tool_name}, params={params}")
        return{
            "status":"success",
            'tool':tool_name,
            "result":f"fake_result_from_{tool_name}"
        }