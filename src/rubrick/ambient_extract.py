"""Ambient-motion gather — the 3rd scan. Ambient motion is scattered across CSS
@keyframes, `infinite` usages, and JS keyframe template literals. We gather the
loops (not the triggered transitions) and hand them to the generic facet extractor
(style_facets), which grounds features + catches novels via the escape.
"""

from __future__ import annotations

import pathlib
import subprocess


def _all_keyframes(css: str) -> list[str]:
    out, i = [], 0
    while True:
        i = css.find("@keyframes", i)
        if i < 0:
            break
        j = css.find("{", i)
        depth = 0
        for k in range(j, len(css)):
            if css[k] == "{":
                depth += 1
            elif css[k] == "}":
                depth -= 1
                if depth == 0:
                    out.append(css[i:k + 1])
                    i = k + 1
                    break
        else:
            break
    return out


def gather_ambient_source(root: str, gcss: str, comps: str) -> str:
    r = pathlib.Path(root)
    css = (r / gcss).read_text() if (r / gcss).exists() else ""
    kf = "\n\n".join(_all_keyframes(css))
    motion = [l.strip() for l in css.splitlines()
              if any(k in l for k in ("--motion", "infinite", "animation"))]

    def grep(args):
        try:
            return subprocess.run(args, capture_output=True, text=True, timeout=20).stdout
        except Exception:
            return ""

    # component keyframe bodies + infinite usages — across ALL source dirs (an ambient loop
    # on a page in src/app is as much identity as one in src/components)
    from rubrick.discover import source_dirs
    dirs = source_dirs(root, comps) or [str(r / comps)]
    comp_kf = grep(["grep", "-rhA5", "@keyframes", *dirs])
    comp_inf = grep(["grep", "-rhoE", r"animation:[^,}`]*(infinite|--motion-ring)[^,}`]*",
                     *dirs])
    comp_kf = "\n".join(comp_kf.splitlines()[:45])
    comp_inf = "\n".join(sorted(set(comp_inf.splitlines()))[:20])

    from rubrick.tailwind import gather_tailwind  # config `animation` + animate-* utilities (no-op if not TW)
    tw = gather_tailwind(root, comps, "ambient")
    return (f"/* global @keyframes */\n{kf}\n\n"
            f"/* global motion tokens/usages */\n" + "\n".join(motion[:25]) + "\n\n"
            f"/* component keyframes */\n{comp_kf}\n\n"
            f"/* infinite/looping usages */\n{comp_inf}" + tw)
