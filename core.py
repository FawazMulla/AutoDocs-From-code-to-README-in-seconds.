import os
import json
import shutil
import git
import tempfile
import re
import stat
# --- CONFIGURATION ---
LANGUAGE_MAP = {
    'requirements.txt': 'Python', 'setup.py': 'Python', 'Pipfile': 'Python', 'pyproject.toml': 'Python', 'main.py': 'Python',
    'package.json': 'Node.js', 'yarn.lock': 'Node.js', 'tsconfig.json': 'TypeScript',
    'Cargo.toml': 'Rust',
    'pom.xml': 'Java', 'build.gradle': 'Java',
    'go.mod': 'Go', 'main.go': 'Go',
    'composer.json': 'PHP',
    'Gemfile': 'Ruby',
    'Dockerfile': 'Docker', 'docker-compose.yml': 'Docker',
    'Makefile': 'Make',
    'CMakeLists.txt': 'C++',
    'pubspec.yaml': 'Dart/Flutter',
    'mix.exs': 'Elixir'
}

TECH_SIGNATURES = {
    'database': {
        'mongo': 'MongoDB', 'mongoose': 'MongoDB', 'sqlalchemy': 'SQL DB', 'psycopg2': 'PostgreSQL', 
        'mysql': 'MySQL', 'redis': 'Redis', 'sqlite': 'SQLite', 'mariadb': 'MariaDB'
    },
    'cloud': {
        'boto3': 'AWS', 'aws-sdk': 'AWS', 'google-cloud': 'GCP', 'azure': 'Azure', 'firebase': 'Firebase'
    },
    'framework': {
        'flask': 'Flask', 'django': 'Django', 'fastapi': 'FastAPI', 'express': 'Express', 
        'react': 'React', 'next': 'Next.js', 'vue': 'Vue.js', 'svelte': 'Svelte',
        'spring': 'Spring Boot', 'laravel': 'Laravel', 'rails': 'Ruby on Rails', 'gin': 'Gin (Go)'
    }
}

IGNORE_DIRS = {'.git', 'node_modules', 'venv', '.env', '__pycache__', 'dist', 'build', 'target', 'vendor', '.idea', '.vscode', '.next'}

class ProjectScanner:
    def __init__(self, path):
        self.original_path = path
        self.path = path
        self.is_remote = path.startswith('http') or path.endswith('.git')
        self.temp_dir = None
        self.metadata = {
            "languages": set(),
            "tech_stack": set(),
            "dependencies": {},
            "scripts": {},
            "structure": "",
            "description": "",
            "entry_point": None
        }

    def setup_path(self):
        """Clones if remote, uses direct path if local."""
        if self.is_remote:
            self.temp_dir = tempfile.mkdtemp()
            try:
                git.Repo.clone_from(self.original_path, self.temp_dir)
                self.path = self.temp_dir
                return self.path
            except Exception as e:
                self.cleanup()
                raise Exception(f"Failed to clone repository: {str(e)}")
        
        if not os.path.exists(self.path):
            raise Exception("Local path does not exist.")
        return self.path

    def cleanup(self):
        """Robust cleanup that handles Windows PermissionError"""
        if self.temp_dir and os.path.exists(self.temp_dir):
            try:
                # helper function to remove read-only files
                def on_rm_error(func, path, exc_info):
                    os.chmod(path, stat.S_IWRITE)
                    func(path)
                
                shutil.rmtree(self.temp_dir, onerror=on_rm_error)
            except Exception as e:
                print(f"Warning: Could not fully clean up temp dir: {e}")

    def scan(self):
        """Main scanning execution."""
        self._scan_tree(self.path)
        return self.metadata

    def _scan_tree(self, root_path):
        """Generates tree and detects tech simultaneously."""
        tree_lines = []
        
        for root, dirs, files in os.walk(root_path):
            # 1. Ignore unwanted directories
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
            
            level = root.replace(root_path, '').count(os.sep)
            
            # Tree View Logic (Limit depth to keep it readable)
            if level < 3:
                indent = '│   ' * level
                subindent = '├── '
                if level > 0:
                    tree_lines.append(f"{indent}{subindent}{os.path.basename(root)}/")
                for f in files:
                    if not f.startswith('.'):
                        tree_lines.append(f"{indent}│   {f}")

            # 2. File Analysis (Detect Language & Tech)
            for f in files:
                file_path = os.path.join(root, f)
                
                # Language Detection
                if f in LANGUAGE_MAP:
                    lang = LANGUAGE_MAP[f]
                    self.metadata["languages"].add(lang)
                    self._extract_dependencies(file_path, lang)
                
                # Tech Stack Scanning (only scan code/config files, max 10kb)
                if f.endswith(('.js', '.ts', '.py', '.json', '.toml', '.go', '.java', '.php', '.rb')):
                    self._scan_file_content(file_path)

        self.metadata["structure"] = "```text\n.\n" + "\n".join(tree_lines) + "\n```"

    def _scan_file_content(self, filepath):
        try:
            with open(filepath, 'r', errors='ignore') as f:
                content = f.read(10000) # Read first 10KB
                content_lower = content.lower()
                
                # Tech Signatures
                for category, signatures in TECH_SIGNATURES.items():
                    for keyword, tech_name in signatures.items():
                        if keyword in content_lower:
                            self.metadata["tech_stack"].add(tech_name)
                
                # Entry Point & Docstring (Python specific heuristic)
                if filepath.endswith('app.py') or filepath.endswith('main.py'):
                    self.metadata["entry_point"] = os.path.basename(filepath)
                    if not self.metadata["description"]:
                        match = re.search(r'"""(.*?)"""', content, re.DOTALL)
                        if match: self.metadata["description"] = match.group(1).strip()
        except: pass

    def _extract_dependencies(self, filepath, language):
        try:
            fname = os.path.basename(filepath)
            if fname == 'package.json':
                with open(filepath) as f:
                    data = json.load(f)
                    self.metadata["dependencies"]["Node.js"] = list(data.get('dependencies', {}).keys())
                    self.metadata["scripts"] = data.get('scripts', {})
                    if data.get('description'): self.metadata["description"] = data.get('description')
            elif fname == 'requirements.txt':
                with open(filepath) as f:
                    self.metadata["dependencies"]["Python"] = [l.strip().split('==')[0] for l in f if l.strip() and not l.startswith('#')]
            elif fname == 'go.mod':
                with open(filepath) as f:
                    self.metadata["dependencies"]["Go"] = [l.split()[1] for l in f if 'require' in l and len(l.split()) > 1]
        except: pass

    def generate_mermaid(self):
        """Generates dynamic architecture diagram based on detected tech."""
        stack = self.metadata["tech_stack"]
        chart = "```mermaid\ngraph TD\n    User[User] --> UI[Client / UI]\n"
        
        # Determine Backend Node
        backend = "Server"
        for tech in stack:
            if "Server" in tech or "API" in tech or "Boot" in tech or "Laravel" in tech:
                backend = tech.replace(" ", "_")
                break
        
        chart += f"    UI --> {backend}[{backend.replace('_', ' ')}]\n"
        
        # Connect DBs and Cloud
        for tech in stack:
            if tech in TECH_SIGNATURES['database'].values():
                chart += f"    {backend} --> {tech}[({tech})]\n"
            if tech in TECH_SIGNATURES['cloud'].values():
                chart += f"    {backend} --> {tech}(({tech}))\n"
        
        chart += "```"
        return chart

    def build_markdown(self, template="Detailed"):
        langs = sorted(list(self.metadata["languages"]))
        stack = sorted(list(self.metadata["tech_stack"]))
        
        # Header
        name = os.path.basename(self.original_path).replace('.git', '')
        if name == "" or name == ".": name = "Project"
        
        md = f"# {name}\n\n"
        
        # Badges
        for l in langs: md += f"![{l}](https://img.shields.io/badge/{l}-Use-blue) "
        md += "![License](https://img.shields.io/badge/license-MIT-green)\n\n"
        
        # Description
        desc = self.metadata["description"] or f"A robust application built using {', '.join(langs)}."
        md += f"## 📝 Description\n{desc}\n\n"
        
        # Architecture
        if template == "Detailed" and stack:
            md += "## 🏗 Architecture\n" + self.generate_mermaid() + "\n\n"
            
        # Tech Stack Table
        if template == "Detailed" and (langs or stack):
            md += "## 🛠 Tech Stack\n| Type | Technologies |\n|---|---|\n"
            md += f"| **Languages** | {', '.join(langs)} |\n"
            if stack: md += f"| **Tools/Frameworks** | {', '.join(stack)} |\n"
            md += "\n"

        # Installation
        md += "## ⚙️ Installation\n"
        md += "### Prerequisites\n"
        for l in langs: md += f"- {l} environment\n"
        md += "\n### Setup\n1. Clone the repository\n```bash\ngit clone <repo_url>\n```\n"
        
        if "Node.js" in langs: md += "2. Install dependencies\n```bash\nnpm install\n```\n"
        elif "Python" in langs: md += "2. Install dependencies\n```bash\npip install -r requirements.txt\n```\n"
        elif "Go" in langs: md += "2. Tidy modules\n```bash\ngo mod tidy\n```\n"
        
        # Usage
        md += "## 🚀 Usage\n"
        if self.metadata["scripts"]:
            md += "| Script | Command |\n|---|---|\n"
            for k,v in self.metadata["scripts"].items():
                if k in ['start', 'dev', 'build', 'test']:
                    md += f"| `{k}` | `npm run {k}` |\n"
            md += "\n"
        elif self.metadata["entry_point"]:
            md += f"Run the application:\n```bash\npython {self.metadata['entry_point']}\n```\n"
        else:
            md += "```bash\n# Add your run command here\n```\n"
            
        # Structure
        md += "## 📂 Project Structure\n" + self.metadata["structure"] + "\n\n"
        
        md += "## 🤝 Contributing\nContributions are welcome! Please open an issue or submit a pull request.\n\n"
        md += "## 📄 License\nThis project is licensed under the MIT License."
        
        return md