import os
import json
import shutil
import git
import tempfile
import re
import stat

# --- CONFIGURATION ---
STD_LIBS = {
    'python': {'os', 'sys', 're', 'json', 'math', 'datetime', 'time', 'random', 'subprocess', 'typing', 'collections', 'threading', 'asyncio', 'logging', 'argparse'},
    'node': {'fs', 'path', 'http', 'https', 'os', 'util', 'events', 'crypto', 'child_process', 'cluster', 'dns', 'net', 'stream', 'querystring'},
    'java': {'java.lang', 'java.util', 'java.io', 'java.net', 'java.math'},
    'go': {'fmt', 'os', 'net', 'time', 'encoding', 'sync', 'strings', 'strconv', 'io', 'log'}
}

IGNORE_DIRS = {
    '.git', 'node_modules', 'venv', '.env', '__pycache__', 
    'dist', 'build', 'target', 'vendor', '.idea', '.vscode', 
    'coverage', '.next', '__mocks__', 'assets', 'bin', 'obj', 'out', '.settings'
}

class DeepScanner:
    def __init__(self, path, custom_context=""):
        self.original_path = path
        self.path = path
        self.custom_context = custom_context
        self.is_remote = path.startswith('http') or path.endswith('.git')
        self.temp_dir = None
        self.metadata = {
            "project_name": "",
            "username": "username",
            "repo_name": "repo",
            "repo_url": "<repo_url>",
            "languages": set(),
            "tech_stack": set(),
            "dependencies": {"Python": set(), "Node.js": set(), "Java": set(), "Go": set()},
            "scripts": {},
            "structure": "",
            "description": "",
            "entry_point": None,      # The actual file (e.g., main.py)
            "entry_point_cmd": None,  # The command class/func (e.g., Main class)
            "api_endpoints": [],
            "license": "Unlicensed",
            "modules": [],            # Classes/Modules for architecture
            "env_vars": set(),
            "tests": [],              # Stores detected test frameworks
            "build_tools": set()      # Maven, Gradle, Poetry, etc.
        }

    def setup_path(self):
        if self.is_remote:
            self.temp_dir = tempfile.mkdtemp()
            try:
                git.Repo.clone_from(self.original_path, self.temp_dir)
                self.path = self.temp_dir
                self.metadata["repo_url"] = self.original_path
                parts = self.original_path.rstrip('/').split('/')
                if len(parts) >= 2:
                    self.metadata["repo_name"] = parts[-1].replace('.git', '')
                    self.metadata["username"] = parts[-2]
                    self.metadata["project_name"] = self.metadata["repo_name"]
            except Exception as e:
                self.cleanup()
                raise Exception(f"Clone failed: {str(e)}")
        else:
            if not os.path.exists(self.path):
                raise Exception("Local path does not exist.")
            self.metadata["project_name"] = os.path.basename(os.path.normpath(self.path))
            try:
                repo = git.Repo(self.path)
                url = repo.remotes.origin.url
                self.metadata["repo_url"] = url
                parts = url.rstrip('/').replace('.git', '').split('/')
                self.metadata["repo_name"] = parts[-1]
                self.metadata["username"] = parts[-2].split(':')[-1]
            except: pass
        return self.path

    def cleanup(self):
        if self.temp_dir and os.path.exists(self.temp_dir):
            try:
                def on_rm_error(func, path, exc_info):
                    os.chmod(path, stat.S_IWRITE)
                    func(path)
                shutil.rmtree(self.temp_dir, onerror=on_rm_error)
            except: pass

    def scan(self):
        self._scan_license()
        self._scan_tree(self.path)
        if not self.metadata["description"]:
            self.metadata["description"] = self._generate_smart_description()
        return self.metadata

    def _generate_smart_description(self):
        name = self.metadata["project_name"].replace('-', ' ').replace('_', ' ').title()
        langs = list(self.metadata["languages"])
        stack = list(self.metadata["tech_stack"])
        
        ptype = "Software Solution"
        if "Api" in name: ptype = "RESTful API"
        elif "Web" in name or "Ui" in name: ptype = "Web Application"
        elif "Lib" in name or "Sdk" in name: ptype = "Library"
        elif "Management" in name or "System" in name: ptype = "Management System"
        
        desc = f"**{name}** is a {ptype}"
        if langs: desc += f" built with **{langs[0]}**"
        
        frameworks = [t.split(': ')[1] for t in stack if 'Framework' in t]
        dbs = [t.split(': ')[1] for t in stack if 'Database' in t]
        
        if frameworks: desc += f", leveraging **{frameworks[0]}** for the architecture"
        if dbs: desc += f" and **{dbs[0]}** for data storage"
        
        desc += "."
        return desc

    def _scan_license(self):
        for f in os.listdir(self.path):
            if f.upper().startswith('LICENSE') or f.upper().startswith('COPYING'):
                try:
                    with open(os.path.join(self.path, f), 'r') as lic_file:
                        content = lic_file.read(100).upper()
                        if "MIT" in content: self.metadata["license"] = "MIT"
                        elif "APACHE" in content: self.metadata["license"] = "Apache 2.0"
                        elif "GNU" in content: self.metadata["license"] = "GPL"
                        else: self.metadata["license"] = "See LICENSE file"
                except: pass
                break

    def _scan_tree(self, root_path):
        tree_lines = []
        for root, dirs, files in os.walk(root_path):
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
            rel_path = os.path.relpath(root, root_path)
            
            level = rel_path.count(os.sep)
            if rel_path == '.': level = 0
            else: level += 1

            if level < 4:
                indent = '│   ' * level
                subindent = '├── '
                if level > 0: tree_lines.append(f"{indent}{subindent}{os.path.basename(root)}/")
                for f in files:
                    if f.endswith(('.java', '.py', '.js', '.ts', '.go', '.json', '.xml', '.md', '.yml')):
                        tree_lines.append(f"{indent}│   {f}")

            for f in files:
                filepath = os.path.join(root, f)
                ext = os.path.splitext(f)[1]
                
                # Config & Build Tools
                if f == 'package.json': 
                    self.metadata["languages"].add("Node.js")
                    self._parse_package_json(filepath)
                elif f == 'requirements.txt': 
                    self.metadata["languages"].add("Python")
                    self._parse_requirements(filepath)
                elif f == 'pom.xml': 
                    self.metadata["languages"].add("Java")
                    self.metadata["build_tools"].add("Maven")
                elif f == 'build.gradle': 
                    self.metadata["languages"].add("Java")
                    self.metadata["build_tools"].add("Gradle")
                elif f == 'go.mod': 
                    self.metadata["languages"].add("Go")

                # Code Analysis
                if ext in ['.py', '.js', '.ts', '.java', '.go']:
                    self._analyze_code(filepath, ext)

        self.metadata["structure"] = "```text\n.\n" + "\n".join(tree_lines) + "\n```"

    def _parse_package_json(self, filepath):
        try:
            with open(filepath) as f:
                data = json.load(f)
                if data.get('name'): self.metadata["project_name"] = data.get('name')
                
                if data.get('main'): 
                    self.metadata["entry_point"] = data.get('main')
                    
                deps = list(data.get('dependencies', {}).keys())
                devDeps = list(data.get('devDependencies', {}).keys())
                
                self.metadata["dependencies"]["Node.js"].update(deps)
                self.metadata["scripts"] = data.get('scripts', {})
                if data.get('description'): self.metadata["description"] = data.get('description')
                
                # Detect Testing Frameworks
                for d in deps + devDeps:
                    if d in ['jest', 'mocha', 'chai', 'supertest']: self.metadata["tests"].append(d)
        except: pass

    def _parse_requirements(self, filepath):
        try:
            with open(filepath) as f:
                deps = [line.split('==')[0].strip() for line in f if line.strip() and not line.startswith('#')]
                self.metadata["dependencies"]["Python"].update(deps)
                for d in deps:
                    if d in ['pytest', 'unittest', 'nose', 'mock']: self.metadata["tests"].append(d)
        except: pass

    def _analyze_code(self, filepath, ext):
        try:
            with open(filepath, 'r', errors='ignore', encoding='utf-8') as f:
                content = f.read()
                fname = os.path.basename(filepath)
                
                # --- PYTHON ---
                if ext == '.py':
                    if 'if __name__ == "__main__":' in content or 'app.run(' in content:
                        self.metadata["entry_point"] = fname
                    
                    classes = re.findall(r'class\s+(\w+)', content)
                    for c in classes: self.metadata["modules"].append(c)

                    imports = re.findall(r'^(?:from|import)\s+([\w-]+)', content, re.MULTILINE)
                    for imp in imports: 
                        if imp not in STD_LIBS['python']: 
                            self.metadata["dependencies"]["Python"].add(imp)

                # --- NODE.JS ---
                elif ext in ['.js', '.ts']:
                    if 'app.listen' in content or 'server.listen' in content:
                        self.metadata["entry_point"] = fname
                    
                    imports = re.findall(r'(?:require|from)\s*[\'"]([@\w/-]+)[\'"]', content)
                    for imp in imports:
                        if not imp.startswith('.') and imp not in STD_LIBS['node']:
                            self.metadata["dependencies"]["Node.js"].add(imp)

                # --- GO ---
                elif ext == '.go':
                    if 'func main()' in content:
                        self.metadata["entry_point"] = fname
                    
                    imports = re.findall(r'"([\w/]+)"', content)
                    for imp in imports:
                        if '.' in imp and '/' in imp:
                            self.metadata["dependencies"]["Go"].add(imp)

                # --- JAVA ---
                elif ext == '.java':
                    class_match = re.search(r'class\s+(\w+)', content)
                    if class_match:
                        self.metadata["modules"].append(class_match.group(1))
                        
                    if "public static void main" in content:
                        self.metadata["entry_point"] = fname
                        if class_match:
                            self.metadata["entry_point_cmd"] = class_match.group(1)
                    
                    imports = re.findall(r'import\s+([\w\.]+);', content)
                    for imp in imports:
                        if not any(x in imp for x in ['java.lang', 'java.util', 'java.io']):
                            self.metadata["dependencies"]["Java"].add(imp)

                # Env Vars (Universal)
                env_matches = re.findall(r'(?:process\.env\.|os\.environ\.get\([\'"]|os\.getenv\([\'"])([A-Z_]+)', content)
                for env in env_matches: self.metadata["env_vars"].add(env)

        except: pass

    def generate_diagrams(self):
        # 1. Component Architecture (Graph)
        chart = "```mermaid\ngraph TD\n"
        
        # Scenario A: Java/Python Class Diagram
        if ( "Java" in self.metadata["languages"] or "Python" in self.metadata["languages"] ) and self.metadata["modules"]:
            entry = self.metadata["entry_point_cmd"] or self.metadata["entry_point"] or "Main"
            if entry.endswith('.py') or entry.endswith('.java'): entry = entry.split('.')[0]
            
            chart += f"    {entry} --> Logic_Layer\n"
            for mod in self.metadata["modules"][:6]:
                if mod != entry: chart += f"    Logic_Layer --> {mod}\n"
        
        # Scenario B: Node/Go Component Diagram
        else:
            chart += "    User[User] --> UI[Client]\n"
            backend = self.metadata["entry_point"] or "Server"
            chart += f"    UI --> {backend}\n"
            
            # Map Frameworks/DBs
            for dep in self.metadata["dependencies"].get("Node.js", []) | self.metadata["dependencies"].get("Python", []):
                if dep in ['mongoose', 'mongodb', 'pg', 'mysql', 'sequelize']:
                    chart += f"    {backend} --> {dep}[({dep} DB)]\n"
                elif dep in ['redis', 'ioredis']:
                    chart += f"    {backend} --> {dep}(({dep} Cache))\n"

        chart += "```\n\n"
        
        # 2. Application Flow (Sequence)
        flow = "```mermaid\nsequenceDiagram\n    participant User\n    participant System\n"
        
        # Detect DB usage for Sequence Diagram
        has_db = any("Database" in t for t in self.metadata["tech_stack"])
        # Fallback check on dependencies
        if not has_db:
             for lang, deps in self.metadata["dependencies"].items():
                 if any(d in ['mongoose', 'mongodb', 'sqlalchemy', 'pymongo', 'mysql', 'pg'] for d in deps):
                     has_db = True
                     break

        if has_db: flow += "    participant DB as Database\n"
        
        flow += "    User->>System: Request\n"
        flow += "    System->>System: Process Logic\n"
        
        if has_db:
            flow += "    System->>DB: Query Data\n    DB-->>System: Return Data\n"
        
        flow += "    System-->>User: Response\n```"
        
        return "### Component Architecture\n" + chart + "### Application Flow\n" + flow

    def build_markdown(self, template="Detailed"):
        m = self.metadata
        langs = sorted(list(m["languages"]))
        
        md = f"# {m['project_name']}\n\n"
        
        if template == "Minimal":
            for l in langs: md += f"![{l}](https://img.shields.io/badge/Language-{l}-blue) "
            md += "\n\n"
            md += f"## 📝 Description\n{m['description']}\n\n"
            if self.custom_context: md += f"> **Context:** {self.custom_context}\n\n"
            md += "## 🛠 Tech Stack\n" + ", ".join(langs) + "\n\n"
            md += "## ⚙️ Installation\n" + self._generate_strict_install(langs)
            md += "## 🚀 Usage\n" + self._generate_strict_usage(langs)
            md += f"## 📄 License\n{m['license']}"
            return md

        # Detailed
        if m['username'] != "username":
            user, repo = m['username'], m['repo_name']
            md += f"[![Stars](https://img.shields.io/github/stars/{user}/{repo}?style=social)](https://github.com/{user}/{repo}/stargazers) "
            md += f"[![Forks](https://img.shields.io/github/forks/{user}/{repo}?style=social)](https://github.com/{user}/{repo}/network/members)\n"
        else:
            for l in langs: md += f"![{l}](https://img.shields.io/badge/Language-{l}-blue) "
        md += f"![License](https://img.shields.io/badge/License-{m['license'].replace(' ', '_')}-green)\n\n"

        md += f"## 📝 Description\n{m['description']}\n\n"
        if self.custom_context: md += f"> **Developer Note:** {self.custom_context}\n\n"
        
        md += "## 📸 Screenshot\n![App Screenshot](https://via.placeholder.com/800x400?text=Application+Screenshot)\n\n"

        md += "## 📑 Table of Contents\n- [Architecture](#-architecture)\n- [Project Structure](#-project-structure)\n- [Installation](#-installation)\n- [Usage](#-usage)\n"
        if m["scripts"]: md += "- [Scripts](#-scripts)\n"
        if any(m["dependencies"].values()): md += "- [Dependencies](#-dependencies)\n"
        if m["tests"]: md += "- [Testing](#-testing)\n"
        md += "- [Contributing](#-contributing)\n- [License](#-license)\n\n"

        md += "## 🏗 Architecture\n" + self.generate_diagrams() + "\n\n"
        md += "## 📂 Project Structure\n" + m["structure"] + "\n\n"
        md += "## ⚙️ Installation\n" + self._generate_strict_install(langs)
        md += "## 🚀 Usage\n" + self._generate_strict_usage(langs)

        # Scripts Section
        if m["scripts"]:
            md += "## 📜 Scripts\n| Command | Description |\n|---|---|\n"
            for k,v in m["scripts"].items():
                md += f"| `npm run {k}` | {v} |\n"
            md += "\n"
        
        # Testing Section
        if m["tests"]:
            md += "## 🧪 Testing\nTo run the tests, execute:\n```bash\n"
            if "jest" in m["tests"]: md += "npm test\n"
            elif "pytest" in m["tests"]: md += "pytest\n"
            else: md += "# Run test command\n"
            md += "```\n\n"

        # Dependencies Section
        has_deps = any(m["dependencies"].values())
        if has_deps:
            md += "## 📦 Dependencies\n"
            for l in langs:
                if m["dependencies"].get(l):
                    md += f"**{l}**\n"
                    for d in list(m["dependencies"][l])[:12]:
                        md += f"- `{d}`\n"
                    md += "\n"

        md += "## 🤝 Contributing\n1. Fork the Project\n2. Create your Feature Branch\n3. Commit your Changes\n4. Push to the Branch\n5. Open a Pull Request\n\n"
        md += f"## 📄 License\nThis project is licensed under the **{m['license']}**."
        return md

    def _generate_strict_install(self, langs):
        steps = f"1. **Clone the repository**\n   ```bash\n   git clone {self.metadata['repo_url']}\n   cd {self.metadata['project_name']}\n   ```\n"
        
        if "Node.js" in langs:
            steps += "2. **Node.js Setup**\n   ```bash\n   npm install\n   ```\n"

        if "Python" in langs:
            steps += "2. **Python Setup**\n   ```bash\n   python -m venv venv\n   source venv/bin/activate\n"
            if os.path.exists(os.path.join(self.path, 'requirements.txt')):
                 steps += "   pip install -r requirements.txt\n"
            else:
                 steps += "   pip install " + " ".join(list(self.metadata["dependencies"]["Python"])[:5]) + "\n"
            steps += "   ```\n"

        if "Java" in langs:
            steps += "2. **Java Setup**\n"
            if "Maven" in self.metadata["build_tools"]:
                steps += "   ```bash\n   mvn clean install\n   ```\n"
            elif "Gradle" in self.metadata["build_tools"]:
                steps += "   ```bash\n   ./gradlew build\n   ```\n"
            else:
                steps += "   ```bash\n   # Raw Java Project: Compile manually\n   javac *.java\n   ```\n"

        if "Go" in langs:
             steps += "2. **Go Setup**\n   ```bash\n   go mod tidy\n   ```\n"
             
        return steps

    def _generate_strict_usage(self, langs):
        cmd = ""
        
        if "Node.js" in langs:
            cmd += "**Node.js:**\n"
            if "start" in self.metadata["scripts"]:
                cmd += "```bash\nnpm start\n```\n"
            else:
                entry = self.metadata["entry_point"] or "index.js"
                cmd += f"```bash\nnode {entry}\n```\n"

        if "Python" in langs:
            cmd += "**Python:**\n"
            entry = self.metadata["entry_point"] or "main.py"
            # Detect FastAPI/Flask specifically for run command
            if "fastapi" in self.metadata["dependencies"]["Python"]:
                cmd += f"```bash\nuvicorn {entry.replace('.py','')}:app --reload\n```\n"
            else:
                cmd += f"```bash\npython {entry}\n```\n"

        if "Java" in langs:
            cmd += "**Java:**\n"
            if "Maven" in self.metadata["build_tools"]:
                cmd += "```bash\nmvn spring-boot:run\n```\n"
            elif "Gradle" in self.metadata["build_tools"]:
                cmd += "```bash\n./gradlew bootRun\n```\n"
            else:
                entry_cls = self.metadata["entry_point_cmd"]
                entry_file = self.metadata["entry_point"]
                if entry_cls and entry_file:
                    cmd += f"```bash\njavac {entry_file}\njava {entry_cls}\n```\n"
                else:
                    cmd += "```bash\njavac Main.java\njava Main\n```\n"
                    
        if "Go" in langs:
            cmd += "**Go:**\n"
            entry = self.metadata["entry_point"] or "main.go"
            cmd += f"```bash\ngo run {entry}\n```\n"

        return cmd

def generate_readme(path, template, context):
    scanner = DeepScanner(path, context)
    try:
        scanner.setup_path()
        scanner.scan()
        return scanner.build_markdown(template)
    finally:
        scanner.cleanup()
        # vaibele