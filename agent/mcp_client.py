class MCPClient:
    def __init__(self):
        self.servers:dict[str,str] = {}

    def register_server(self,tool_name:str,endpoint:str):
        """注册某个工具对应的mcp地址"""
        self.servers[tool_name] = endpoint

    def call(self,tool_name:str,params:dict)->dict:
        """
        统一调用入口：
        1. 查 tool_name 对应哪个 server
        2. 本地就直接调，远程就发 HTTP 请求
        3. 返回结果
        """
        server = self.servers.get(tool_name,"local")

        if server == "local":
            return self._call_local(tool_name,params)
        else:
            return self._call_remote(server,tool_name,params)
        
    def _call_local(self, tool_name:str ,paramas:dict)->dict:
        """本地调用"""
        print(f"[mcp] local call ->{tool_name},paramas={paramas}")
        return{
            "status":"success",
            "tool":tool_name,
            "result":f"fake_result_from_{tool_name}"
        }
    
    def _call_remote(self,server:str,tool_name:str,paramas:dict):
        """远程HTTP调用(TODO)"""
        raise NotImplementedError(f"远程调用未实现{server}")