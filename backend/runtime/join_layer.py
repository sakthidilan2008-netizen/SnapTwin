"""
backend/runtime/join_layer.py

Joins Stage 3 static graph data with Stage 4 runtime observations.
"""
from backend.models.graph import DependencyAnalysis
from backend.runtime.runtime_models import RuntimeModule, StaticRuntimeJoinNode, JoinResult

class StaticRuntimeJoin:
    def join(
        self, 
        static_analysis: DependencyAnalysis, 
        runtime_modules: list[RuntimeModule]
    ) -> list[StaticRuntimeJoinNode]:
        """
        Compares the static PE dependency graph against runtime-loaded modules.
        Does not assert causality.
        """
        joins = []
        
        static_map = {n.name.lower(): n for n in static_analysis.nodes if n.depth > 0}
        runtime_map = {m.name.lower(): m for m in runtime_modules}
        
        all_names = set(static_map.keys()).union(set(runtime_map.keys()))
        
        for name in all_names:
            static_node = static_map.get(name)
            runtime_mod = runtime_map.get(name)
            
            static_path = static_node.resolved_path if static_node else None
            runtime_path = runtime_mod.absolute_path if runtime_mod else None
            
            if static_node and runtime_mod:
                res = JoinResult.STATIC_AND_RUNTIME_CONFIRMED
            elif static_node:
                res = JoinResult.STATIC_ONLY
            else:
                res = JoinResult.RUNTIME_ONLY
                
            joins.append(StaticRuntimeJoinNode(
                module_name=static_node.name if static_node else runtime_mod.name,
                static_path=static_path,
                runtime_path=runtime_path,
                join_result=res
            ))
            
        return joins
