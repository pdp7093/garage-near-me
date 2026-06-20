import os
import glob

def revert_html_files():
    for file in glob.glob('f:/garage-near-me/frontend/**/*.html', recursive=True):
        try:
            with open(file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            updated = False
            target_str_1 = '<link rel="manifest" href="/manifest.json">\n  <link rel="icon" type="image/png" href="/assets/gnm_app_logo.png">\n  <link rel="apple-touch-icon" href="/assets/gnm_app_logo.png">'
            if target_str_1 in content:
                content = content.replace(target_str_1, '<link rel="manifest" href="/manifest.json">')
                updated = True
                
            target_str_2 = '<link rel="manifest" href="/mechanic/manifest.json">\n  <link rel="icon" type="image/png" href="/assets/gnm_app_logo.png">\n  <link rel="apple-touch-icon" href="/assets/gnm_app_logo.png">'
            if target_str_2 in content:
                content = content.replace(target_str_2, '<link rel="manifest" href="/mechanic/manifest.json">')
                updated = True

            if updated:
                with open(file, 'w', encoding='utf-8') as f:
                    f.write(content)
                print(f"Reverted {file}")
        except Exception as e:
            print(f"Error on {file}: {e}")

if __name__ == "__main__":
    revert_html_files()
