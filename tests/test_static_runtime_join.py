"""
tests/test_static_runtime_join.py

Tests joining static dependencies with runtime observed modules.
"""
from backend.runtime.join_layer import StaticRuntimeJoin
from backend.runtime.runtime_models import RuntimeModule, JoinResult
from backend.models.graph import DependencyAnalysis, DependencyNode, NodeKind

def test_join_static_and_runtime_confirmed():
    a = DependencyAnalysis(application_id="1", root_path="app.exe")
    a.nodes.append(DependencyNode(node_id="n1", kind=NodeKind.DLL, name="foo.dll", depth=1))
    
    mods = [RuntimeModule(name="foo.dll", absolute_path="C:/foo.dll")]
    
    joiner = StaticRuntimeJoin()
    joins = joiner.join(a, mods)
    
    assert len(joins) == 1
    assert joins[0].module_name == "foo.dll"
    assert joins[0].join_result == JoinResult.STATIC_AND_RUNTIME_CONFIRMED

def test_join_static_only():
    a = DependencyAnalysis(application_id="1", root_path="app.exe")
    a.nodes.append(DependencyNode(node_id="n1", kind=NodeKind.DLL, name="missing_at_runtime.dll", depth=1))
    
    joiner = StaticRuntimeJoin()
    joins = joiner.join(a, [])
    
    assert len(joins) == 1
    assert joins[0].module_name == "missing_at_runtime.dll"
    assert joins[0].join_result == JoinResult.STATIC_ONLY

def test_join_runtime_only():
    a = DependencyAnalysis(application_id="1", root_path="app.exe")
    # depth=0 is root, not a dependency
    a.nodes.append(DependencyNode(node_id="root", kind=NodeKind.EXE, name="app.exe", depth=0))
    
    mods = [RuntimeModule(name="injected.dll", absolute_path="C:/injected.dll")]
    
    joiner = StaticRuntimeJoin()
    joins = joiner.join(a, mods)
    
    assert len(joins) == 1
    assert joins[0].module_name == "injected.dll"
    assert joins[0].join_result == JoinResult.RUNTIME_ONLY
