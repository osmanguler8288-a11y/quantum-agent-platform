from agent.state import AgentState,TaskStatus

def make_plan_node(planner):
    def plan_node(state: dict) -> dict:
        query =state.get("user_query","unknow") 
        
        ag_state = AgentState(task_id=state.get("task_id","unknow"),user_query = query)
        ag_state = planner.plan(ag_state)

        state["thinking"] = ag_state.thinking
        state["plan"] = ag_state.plan
        print(f"[workflow] plan: {len(ag_state.plan)} steps, thinking: {len(ag_state.thinking)} chars")
        return state
    return plan_node