// ═══════════════════════════════════════════
// GNM MULTI-LANGUAGE SYSTEM (i18n.js)
// Mechanic side: hinglish (default), hindi, gujarati
// ═══════════════════════════════════════════

const SUPPORTED_LANGUAGES = ['hinglish', 'hindi', 'gujarati'];
const DEFAULT_LANGUAGE = 'hinglish';

let currentTranslations = {};
let currentLang = DEFAULT_LANGUAGE;

// Mechanic ki saved language nikalo (localStorage se — profile API se bhi le sakte hain baad mein)
function getMechanicLanguage() {
    const saved = localStorage.getItem('mechanic_lang');
    return SUPPORTED_LANGUAGES.includes(saved) ? saved : DEFAULT_LANGUAGE;
}

function setMechanicLanguage(lang) {
    if (!SUPPORTED_LANGUAGES.includes(lang)) return;
    localStorage.setItem('mechanic_lang', lang);
    applyLanguage(lang);
}

// Language JSON file load karo
async function loadLanguageFile(lang) {
    try {
        const res = await fetch(`/lang/${lang}.json`);
        if (!res.ok) throw new Error('Language file not found: ' + lang);
        return await res.json();
    } catch (err) {
        console.error('i18n load error:', err);
        // Fallback: hinglish load karo agar chosen language fail ho jaye
        if (lang !== DEFAULT_LANGUAGE) {
            const res = await fetch(`/lang/${DEFAULT_LANGUAGE}.json`);
            return await res.json();
        }
        return {};
    }
}

// Page ke saare data-i18n elements ka text replace karo
function applyTranslationsToDOM() {
    document.querySelectorAll('[data-i18n]').forEach((el) => {
        const key = el.getAttribute('data-i18n');
        if (currentTranslations[key]) {
            el.textContent = currentTranslations[key];
        }
    });
}

// JS ke andar text ke liye helper — jaise: t('dashboard_offline')
function t(key) {
    return currentTranslations[key] || key;
}

// Language apply karo — DOM update + JS translations dono
async function applyLanguage(lang) {
    currentLang = lang;
    currentTranslations = await loadLanguageFile(lang);
    applyTranslationsToDOM();
    // Dusre JS ko batao ki translations ready hain (dynamic content ke liye)
    document.dispatchEvent(new CustomEvent('i18n:ready'));
}

// Page load hote hi mechanic ki language apply karo
document.addEventListener('DOMContentLoaded', () => {
    applyLanguage(getMechanicLanguage());
});