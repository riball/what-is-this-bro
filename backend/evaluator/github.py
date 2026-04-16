"""
Fetches public GitHub repo metadata to enrich the project evaluation.
No auth token required for public repos (60 req/hr limit).
"""
import re, requests

GH_API = "https://api.github.com"

def parse_github_url(url: str) -> tuple[str,str] | None:
    """Return (owner, repo) or None."""
    patterns = [
        r"github\.com[/:]([^/]+)/([^/\s.]+?)(?:\.git)?$",
        r"github\.com[/:]([^/]+)/([^/\s.]+)",
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1), m.group(2).rstrip("/")
    return None

def fetch_github_meta(owner: str, repo: str) -> dict:
    headers = {"Accept": "application/vnd.github.v3+json"}
    out = {}

    try:
        r = requests.get(f"{GH_API}/repos/{owner}/{repo}", headers=headers, timeout=8)
        if r.status_code == 200:
            d = r.json()
            out["name"]        = d.get("name","")
            out["description"] = d.get("description","") or ""
            out["stars"]       = d.get("stargazers_count", 0)
            out["forks"]       = d.get("forks_count", 0)
            out["open_issues"] = d.get("open_issues_count", 0)
            out["language"]    = d.get("language","")
            out["topics"]      = d.get("topics", [])
            out["license"]     = d.get("license",{}).get("name","None") if d.get("license") else "None"
            out["created_at"]  = d.get("created_at","")
            out["updated_at"]  = d.get("updated_at","")
            out["size_kb"]     = d.get("size", 0)
            out["default_branch"] = d.get("default_branch","main")
            out["has_wiki"]    = d.get("has_wiki", False)
            out["has_issues"]  = d.get("has_issues", False)
            out["archived"]    = d.get("archived", False)
        elif r.status_code == 404:
            out["error"] = "Repository not found or is private."
            return out
        elif r.status_code == 403:
            out["error"] = "GitHub API rate limit reached. Try again in a minute."
            return out
    except Exception as e:
        out["error"] = str(e)
        return out

    # Contributors count
    try:
        cr = requests.get(f"{GH_API}/repos/{owner}/{repo}/contributors",
                          headers=headers, params={"per_page":1,"anon":"true"}, timeout=5)
        # GitHub returns Link header with last page = contributor count
        link = cr.headers.get("Link","")
        m = re.search(r'page=(\d+)>; rel="last"', link)
        out["contributors"] = int(m.group(1)) if m else (len(cr.json()) if cr.status_code==200 else 0)
    except Exception:
        out["contributors"] = 0

    # Latest release
    try:
        rr = requests.get(f"{GH_API}/repos/{owner}/{repo}/releases/latest",
                          headers=headers, timeout=5)
        if rr.status_code == 200:
            rd = rr.json()
            out["latest_release"] = rd.get("tag_name","")
            out["release_name"]   = rd.get("name","")
    except Exception:
        pass

    # Commit frequency (last 4 weeks)
    try:
        par = requests.get(f"{GH_API}/repos/{owner}/{repo}/stats/participation",
                           headers=headers, timeout=6)
        if par.status_code == 200:
            all_commits = par.json().get("all",[])
            out["commits_last_4w"] = sum(all_commits[-4:]) if len(all_commits)>=4 else sum(all_commits)
    except Exception:
        pass

    return out

def github_credibility_flags(meta: dict) -> list[str]:
    flags = []
    if meta.get("stars",0) == 0 and meta.get("contributors",0) <= 1:
        flags.append("Single contributor with no community traction")
    if meta.get("open_issues",0) > 50:
        flags.append(f"{meta['open_issues']} open issues — potential quality concerns")
    if meta.get("license","None") == "None":
        flags.append("No license — unclear usage rights")
    if not meta.get("description","").strip():
        flags.append("No repository description")
    if meta.get("archived"):
        flags.append("Repository is archived — no longer maintained")
    if meta.get("commits_last_4w",1) == 0:
        flags.append("No commits in the last 4 weeks — possibly abandoned")
    return flags
