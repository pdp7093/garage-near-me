import os
import glob

def update_html_files():
    for file in glob.glob('f:/garage-near-me/frontend/**/*.html', recursive=True):
        try:
            with open(file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            updated = False
            if '<link rel="manifest" href="/manifest.json">' in content and 'apple-touch-icon' not in content:
                content = content.replace(
                    '<link rel="manifest" href="/manifest.json">', 
                    '<link rel="manifest" href="/manifest.json">\n  <link rel="icon" type="image/png" href="/assets/gnm_app_logo.png">\n  <link rel="apple-touch-icon" href="/assets/gnm_app_logo.png">'
                )
                updated = True
                
            if '<link rel="manifest" href="/mechanic/manifest.json">' in content and 'apple-touch-icon' not in content:
                content = content.replace(
                    '<link rel="manifest" href="/mechanic/manifest.json">', 
                    '<link rel="manifest" href="/mechanic/manifest.json">\n  <link rel="icon" type="image/png" href="/assets/gnm_app_logo.png">\n  <link rel="apple-touch-icon" href="/assets/gnm_app_logo.png">'
                )
                updated = True

            if updated:
                with open(file, 'w', encoding='utf-8') as f:
                    f.write(content)
                print(f"Updated {file}")
        except Exception as e:
            print(f"Error on {file}: {e}")

if __name__ == "__main__":
    update_html_files()
