Name:		janino
Version:	3.1.12
Release:	1
Summary:	Embedded Java compiler
Group:		Development/Java
License:	BSD
URL:		https://github.com/janino-compiler/janino
Source0:	https://github.com/janino-compiler/janino/archive/refs/tags/v%{version}.tar.gz#/janino-%{version}.tar.gz

BuildArch:	noarch
# Literal, so the first rpmbuild -bs records them before sysjar is installed.
BuildRequires:	maven
BuildRequires:	java-current-devel
BuildSystem:	maven
Obsoletes:	janino-javadoc < %{version}

%description
Janino compiles expressions, scripts, class bodies and source files in
memory. 3.1.12 is the last release. This package ships janino, the
commons-compiler API, and the JDK javax.tools implementation. The
optional Ant adapter is omitted: the system Ant package has no Maven
coordinate. Tests are skipped.

%prep
%autosetup -n janino-%{version}
# The reactor POM lives in a subdirectory and points at modules with
# "../". The bundled Ant jar is a prebuilt binary, and AntCompilerAdapter
# is the only class that imports it.
rm -f janino/lib/ant-1.7.1.jar
rm -f janino/src/main/java/org/codehaus/janino/AntCompilerAdapter.java
python - <<'PY'
import xml.etree.ElementTree as ET
from pathlib import Path

ET.register_namespace("", "http://maven.apache.org/POM/4.0.0")
ET.register_namespace("xsi", "http://www.w3.org/2001/XMLSchema-instance")

def local(tag):
    return tag.rsplit("}", 1)[-1]

def q(parent, name):
    if parent.tag.startswith("{"):
        return parent.tag.split("}", 1)[0] + "}" + name
    return name

def find_child(elem, name):
    if elem is None:
        return None
    for child in elem:
        if local(child.tag) == name:
            return child
    return None

def artifact_of(elem):
    found = find_child(elem, "artifactId")
    return (found.text or "").strip() if found is not None else ""

def kids(elem):
    if elem is None:
        return []
    return list(elem)

drop_plugins = {
    "maven-surefire-plugin",
    "maven-bundle-plugin",
    "maven-jarsigner-plugin",
    "maven-javadoc-plugin",
    "maven-source-plugin",
    "nexus-staging-maven-plugin",
}

parent_path = Path("janino-parent/pom.xml")
tree = ET.parse(parent_path)
root = tree.getroot()
props = find_child(root, "properties")
if props is None:
    raise SystemExit("properties missing")
removed_props = []
for child in list(props):
    name = local(child.tag)
    if name in {"maven.compiler.executable", "maven.compiler.fork"}:
        props.remove(child)
        removed_props.append(name)
source = find_child(props, "maven.compiler.source")
target = find_child(props, "maven.compiler.target")
if source is None or target is None:
    raise SystemExit("compiler source or target missing")
if (source.text or "").strip() != "1.7" or (target.text or "").strip() != "1.7":
    raise SystemExit("compiler level is not 1.7")
if find_child(props, "maven.compiler.release") is not None:
    raise SystemExit("compiler release must stay unset")

modules = find_child(root, "modules")
if modules is None:
    raise SystemExit("modules missing")
for child in list(modules):
    modules.remove(child)
for name in ("commons-compiler", "commons-compiler-jdk", "janino"):
    elem = ET.Element(q(modules, "module"))
    elem.text = name
    modules.append(elem)

build = find_child(root, "build")
plugins = find_child(build, "plugins")
if plugins is None:
    raise SystemExit("plugins missing")
removed = []
for child in list(plugins):
    if local(child.tag) != "plugin":
        continue
    art = artifact_of(child)
    if art in drop_plugins:
        plugins.remove(child)
        removed.append(art)
        continue
    if art in {"maven-jar-plugin", "maven-compiler-plugin"}:
        for item in list(child):
            if local(item.tag) == "version":
                child.remove(item)
    if art == "maven-jar-plugin":
        conf = find_child(child, "configuration")
        archive = find_child(conf, "archive")
        for item in kids(archive):
            if local(item.tag) == "manifestFile":
                archive.remove(item)
management = find_child(build, "pluginManagement")
if management is not None:
    build.remove(management)
if find_child(root, "profiles") is not None:
    root.remove(find_child(root, "profiles"))

def plugin_named(parent, art):
    box = find_child(parent, "plugins")
    for child in kids(box):
        if artifact_of(child) == art:
            return child
    return None

def has_named(elem, name):
    return any(local(item.tag) == name for item in kids(elem))

jar = plugin_named(build, "maven-jar-plugin")
compiler = plugin_named(build, "maven-compiler-plugin")
if (
    set(removed) != drop_plugins
    or set(removed_props) != {"maven.compiler.executable", "maven.compiler.fork"}
    or jar is None
    or compiler is None
    or has_named(jar, "version")
    or has_named(compiler, "version")
    or has_named(find_child(find_child(jar, "configuration"), "archive"), "manifestFile")
    or [((child.text or "").strip()) for child in modules]
    != ["commons-compiler", "commons-compiler-jdk", "janino"]
    or find_child(build, "pluginManagement") is not None
    or find_child(root, "profiles") is not None
):
    raise SystemExit(
        f"parent props={removed_props} removed={removed} modules="
        f"{[ (c.text or '').strip() for c in modules ]}"
    )
tree.write(Path("pom.xml"), encoding="UTF-8", xml_declaration=True)
parent_path.unlink()

expected_deps = {
    "commons-compiler": 1,
    "commons-compiler-jdk": 0,
    "janino": 3,
}
expected_plugins = {
    "commons-compiler": {"maven-bundle-plugin"},
    "commons-compiler-jdk": {"maven-bundle-plugin"},
    "janino": {"maven-bundle-plugin", "maven-surefire-plugin"},
}
for name, dep_count in expected_deps.items():
    path = Path(name) / "pom.xml"
    tree = ET.parse(path)
    root = tree.getroot()
    parent = find_child(root, "parent")
    relative = find_child(parent, "relativePath")
    if relative is None:
        raise SystemExit(f"{name} relativePath missing")
    relative.text = ".."
    deps = find_child(root, "dependencies")
    removed_deps = 0
    for child in kids(deps):
        if local(child.tag) != "dependency":
            continue
        group_el = find_child(child, "groupId")
        group = (group_el.text or "").strip() if group_el is not None else ""
        art = artifact_of(child)
        scope_el = find_child(child, "scope")
        scope = (scope_el.text or "").strip() if scope_el is not None else ""
        if scope == "test" or (group == "org.apache.ant" and art == "ant"):
            deps.remove(child)
            removed_deps += 1
    if deps is not None and not list(deps):
        root.remove(deps)
    build = find_child(root, "build")
    plugins = find_child(build, "plugins")
    removed_plugins = set()
    for child in kids(plugins):
        if local(child.tag) != "plugin":
            continue
        art = artifact_of(child)
        if art in {"maven-bundle-plugin", "maven-surefire-plugin"}:
            plugins.remove(child)
            removed_plugins.add(art)
    if plugins is not None and not list(plugins):
        build.remove(plugins)
    if build is not None and not list(build):
        root.remove(build)
    if find_child(root, "profiles") is not None:
        root.remove(find_child(root, "profiles"))
    if (
        removed_deps != dep_count
        or removed_plugins != expected_plugins[name]
        or (relative.text or "").strip() != ".."
        or find_child(root, "profiles") is not None
    ):
        raise SystemExit(
            f"{name} deps={removed_deps} plugins={removed_plugins} "
            f"rel={(relative.text or '').strip()}"
        )
    tree.write(path, encoding="UTF-8", xml_declaration=True)

if Path("janino-parent/pom.xml").exists() or not Path("pom.xml").is_file():
    raise SystemExit("reactor pom was not moved")
if Path("janino/src/main/java/org/codehaus/janino/AntCompilerAdapter.java").exists():
    raise SystemExit("Ant adapter remains")
if list(Path(".").rglob("*.jar")):
    raise SystemExit("prebuilt jar remains")
PY

%files -f .mfiles
%doc LICENSE README.md
