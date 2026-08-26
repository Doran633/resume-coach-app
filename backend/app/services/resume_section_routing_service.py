from collections import OrderedDict


ROUTE_ORDER = ["实习经历", "项目经历", "科研经历", "竞赛获奖", "竞赛经历", "开源经历", "校园 / 社团经历"]
META_ROUTE = {
    "实习经历": "实习经历", "科研经历": "科研经历", "竞赛获奖": "竞赛获奖", "竞赛经历": "竞赛经历",
    "开源经历": "开源经历", "校园 / 社团经历": "校园 / 社团经历",
}


def route_resume_projects(projects: list[dict]) -> list[tuple[str, list[dict]]]:
    groups: dict[str, list[dict]] = OrderedDict((key, []) for key in ROUTE_ORDER)
    seen_source_routes: dict[str, str] = {}
    count = 0
    for project in projects:
        route = META_ROUTE.get(str(project.get("meta") or ""), "项目经历")
        source_id = str(project.get("source_experience_id") or "")
        if source_id and source_id in seen_source_routes and seen_source_routes[source_id] != route:
            route = seen_source_routes[source_id]
        elif source_id:
            seen_source_routes[source_id] = route
        groups[route].append(project)
        count += 1
    routed = [(key, groups[key]) for key in ROUTE_ORDER if groups[key]]
    assert sum(len(items) for _, items in routed) == count
    return routed
