from pathlib import Path
import secrets

def main():
    root = Path(__file__).resolve().parent.parent
    env = root / '.env'
    if not env.exists():
        env.write_text((root / '.env.example').read_text(encoding='utf-8'), encoding='utf-8')
    content = env.read_text(encoding='utf-8')
    if 'SECRET_KEY=CHANGE_ME' in content:
        env.write_text(content.replace('SECRET_KEY=CHANGE_ME', 'SECRET_KEY=' + secrets.token_urlsafe(48)), encoding='utf-8')
        print('Generated a random signing key in .env. Keep this file private.')
    else:
        print('Existing .env preserved.')

if __name__ == '__main__':
    main()
