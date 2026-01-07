import os
import json
import requests
import base64
from collections import defaultdict
from datetime import datetime

# Configuration
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
USERNAME = os.environ.get('USERNAME', 'ShauryaDusht')
EXCLUDED_LANGUAGES = ['Jupyter Notebook', 'HTML', 'CSS', 'SCSS', 'Markdown']
TARGET_LANGUAGES = ['Python', 'Java', 'Go', 'JavaScript', 'TypeScript', 'C++', 'C']

# File extensions mapping
LANGUAGE_EXTENSIONS = {
    'Python': ['.py'],
    'Java': ['.java'],
    'Go': ['.go'],
    'JavaScript': ['.js', '.jsx'],
    'TypeScript': ['.ts', '.tsx'],
    'C++': ['.cpp', '.cc', '.cxx', '.hpp', '.h'],
    'C': ['.c', '.h'],
}

# Create reverse mapping
EXT_TO_LANGUAGE = {}
for lang, exts in LANGUAGE_EXTENSIONS.items():
    for ext in exts:
        EXT_TO_LANGUAGE[ext] = lang

def get_headers():
    return {
        'Authorization': f'token {GITHUB_TOKEN}',
        'Accept': 'application/vnd.github.v3+json'
    }

def get_all_repos():
    """Get all non-forked repositories for the user"""
    repos = []
    page = 1
    
    while True:
        url = f'https://api.github.com/users/{USERNAME}/repos?per_page=100&page={page}'
        response = requests.get(url, headers=get_headers())
        
        if response.status_code != 200:
            print(f"Error fetching repos: {response.status_code}")
            break
        
        data = response.json()
        if not data:
            break
        
        # Filter out forked repos
        repos.extend([repo for repo in data if not repo.get('fork', False)])
        page += 1
    
    print(f"Found {len(repos)} non-forked repositories")
    return repos

def count_lines_in_content(content):
    """Count non-empty lines in content"""
    try:
        lines = content.split('\n')
        # Count non-empty, non-whitespace lines
        return sum(1 for line in lines if line.strip())
    except:
        return 0

def get_language_from_extension(filename):
    """Determine language from file extension"""
    ext = os.path.splitext(filename)[1].lower()
    return EXT_TO_LANGUAGE.get(ext)

def process_tree(repo_name, tree_sha, path=''):
    """Recursively process repository tree to count lines"""
    url = f'https://api.github.com/repos/{USERNAME}/{repo_name}/git/trees/{tree_sha}?recursive=1'
    response = requests.get(url, headers=get_headers())
    
    if response.status_code != 200:
        print(f"Error fetching tree for {repo_name}: {response.status_code}")
        return {}
    
    tree_data = response.json()
    language_lines = defaultdict(int)
    
    for item in tree_data.get('tree', []):
        if item['type'] != 'blob':
            continue
        
        filename = item['path']
        language = get_language_from_extension(filename)
        
        if not language or language in EXCLUDED_LANGUAGES:
            continue
        
        # Fetch file content
        try:
            blob_url = f'https://api.github.com/repos/{USERNAME}/{repo_name}/git/blobs/{item["sha"]}'
            blob_response = requests.get(blob_url, headers=get_headers())
            
            if blob_response.status_code == 200:
                blob_data = blob_response.json()
                
                # Decode base64 content
                if blob_data.get('encoding') == 'base64':
                    content = base64.b64decode(blob_data['content']).decode('utf-8', errors='ignore')
                    lines = count_lines_in_content(content)
                    language_lines[language] += lines
                    
        except Exception as e:
            print(f"Error processing {filename} in {repo_name}: {str(e)}")
            continue
    
    return language_lines

def count_all_lines():
    """Count lines of code across all repositories"""
    repos = get_all_repos()
    total_language_lines = defaultdict(int)
    repo_stats = {}
    
    for i, repo in enumerate(repos, 1):
        repo_name = repo['name']
        print(f"\n[{i}/{len(repos)}] Processing: {repo_name}")
        
        try:
            # Get default branch
            default_branch = repo.get('default_branch', 'main')
            
            # Get the tree SHA
            branch_url = f'https://api.github.com/repos/{USERNAME}/{repo_name}/branches/{default_branch}'
            branch_response = requests.get(branch_url, headers=get_headers())
            
            if branch_response.status_code != 200:
                print(f"Skipping {repo_name}: Could not fetch branch info")
                continue
            
            tree_sha = branch_response.json()['commit']['commit']['tree']['sha']
            
            # Count lines in this repo
            repo_lines = process_tree(repo_name, tree_sha)
            repo_stats[repo_name] = dict(repo_lines)
            
            # Add to total
            for lang, lines in repo_lines.items():
                total_language_lines[lang] += lines
                print(f"  {lang}: {lines:,} lines")
                
        except Exception as e:
            print(f"Error processing {repo_name}: {str(e)}")
            continue
    
    return dict(total_language_lines), repo_stats

def generate_markdown_table(language_lines):
    """Generate markdown table for README"""
    if not language_lines:
        return "No code statistics available yet."
    
    # Sort by lines (descending)
    sorted_languages = sorted(language_lines.items(), key=lambda x: x[1], reverse=True)
    
    total_lines = sum(language_lines.values())
    
    markdown = "| Language | Lines of Code | Percentage |\n"
    markdown += "|----------|---------------|------------|\n"
    
    for lang, lines in sorted_languages:
        percentage = (lines / total_lines * 100) if total_lines > 0 else 0
        bar_length = int(percentage / 2)
        bar = '█' * bar_length + '░' * (50 - bar_length)
        markdown += f"| **{lang}** | {lines:,} | {bar} {percentage:.1f}% |\n"
    
    markdown += f"\n**Total Lines of Code:** {total_lines:,}\n"
    
    return markdown

def generate_visual_stats(language_lines):
    """Generate visual representation"""
    if not language_lines:
        return ""
    
    sorted_languages = sorted(language_lines.items(), key=lambda x: x[1], reverse=True)
    total_lines = sum(language_lines.values())
    
    visual = "\n```text\n"
    
    for lang, lines in sorted_languages[:10]:  # Top 10
        percentage = (lines / total_lines * 100) if total_lines > 0 else 0
        bar_length = int(percentage / 2)
        bar = '█' * bar_length
        visual += f"{lang:<15} {bar:<50} {lines:>10,} lines ({percentage:>5.1f}%)\n"
    
    visual += "```\n"
    
    return visual

def update_readme(stats_markdown, visual_stats):
    """Update README.md with statistics"""
    try:
        with open('README.md', 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        print("README.md not found!")
        return
    
    # Define markers
    start_marker = '<!-- LOC-STATS:START -->'
    end_marker = '<!-- LOC-STATS:END -->'
    
    # Create new stats section
    timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
    new_section = f"{start_marker}\n\n"
    new_section += f"**Last Updated:** {timestamp}\n\n"
    new_section += stats_markdown + "\n\n"
    new_section += visual_stats + "\n"
    new_section += end_marker
    
    # Check if markers exist
    if start_marker in content and end_marker in content:
        # Replace existing section
        start_idx = content.find(start_marker)
        end_idx = content.find(end_marker) + len(end_marker)
        new_content = content[:start_idx] + new_section + content[end_idx:]
    else:
        # Append to end
        new_content = content + "\n\n" + new_section
    
    with open('README.md', 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print("\nREADME.md updated successfully!")

def save_json_stats(language_lines, repo_stats):
    """Save detailed statistics to JSON file""" 
    stats = {
        'timestamp': datetime.utcnow().isoformat(),
        'total_lines': sum(language_lines.values()),
        'languages': language_lines,
        'repositories': repo_stats
    }
    
    with open('loc_stats.json', 'w') as f:
        json.dump(stats, f, indent=2)
    
    print("Statistics saved to loc_stats.json")

def main():
    print(f"Starting LOC counter for user: {USERNAME}")
    print("=" * 60)
    
    # Count all lines
    language_lines, repo_stats = count_all_lines()
    
    if not language_lines:
        print("\nNo code found!")
        return
    
    print("\n" + "=" * 60)
    print("📊 FINAL STATISTICS")
    print("=" * 60)
    
    sorted_langs = sorted(language_lines.items(), key=lambda x: x[1], reverse=True)
    for lang, lines in sorted_langs:
        print(f"{lang:<15} {lines:>10,} lines")
    
    print(f"\n{'Total':<15} {sum(language_lines.values()):>10,} lines")
    
    # Generate markdown
    stats_markdown = generate_markdown_table(language_lines)
    visual_stats = generate_visual_stats(language_lines)
    
    # Update README
    update_readme(stats_markdown, visual_stats)
    
    # Save JSON
    save_json_stats(language_lines, repo_stats)
    
    print("\nAll done!")

if __name__ == '__main__':
    main()