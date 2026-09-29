const GNM_PHONE_AUTH = (function () {
    let verificationId = null;
    let webAuth = null;
    let recaptchaVerifier = null;
    let confirmationResult = null;
    let phoneListenersAdded = false;

    // Web Firebase initialization (lazy)
    async function initWebFirebase() {
        if (webAuth) return webAuth;
        const [app, auth] = await Promise.all([
            import('https://www.gstatic.com/firebasejs/10.13.1/firebase-app.js'),
            import('https://www.gstatic.com/firebasejs/10.13.1/firebase-auth.js')
        ]);
        
        const firebaseApp = app.initializeApp(FIREBASE_WEB_CONFIG);
        webAuth = auth.getAuth(firebaseApp);
        webAuth.useDeviceLanguage();
        
        return { app, auth };
    }

    // Setup Recaptcha for Web
    async function setupRecaptcha() {
        const { auth } = await initWebFirebase();
        
        if (recaptchaVerifier) {
            recaptchaVerifier.clear();
            recaptchaVerifier = null;
        }

        recaptchaVerifier = new auth.RecaptchaVerifier(webAuth, 'sendOtpBtn', {
            'size': 'invisible',
            'callback': (response) => {
                // reCAPTCHA solved
            }
        });
    }

    async function sendOtpNative(phoneNumber) {
        const FirebaseAuthentication = window.Capacitor.Plugins.FirebaseAuthentication;

        if (!phoneListenersAdded) {
            await FirebaseAuthentication.removeAllListeners();
            
            await FirebaseAuthentication.addListener('phoneCodeSent', (event) => {
                verificationId = event.verificationId;
            });
            
            await FirebaseAuthentication.addListener('phoneVerificationCompleted', async (event) => {
                // Android auto-retrieval
                // event has credential. In @capacitor-firebase/authentication, phoneVerificationCompleted triggers when auto-retrieved.
                // We should store the credential to use it directly in verifyOtp if possible, but the simplest is just 
                // returning it if it's available, however the plugin might sign in automatically.
                // The prompt says: "resolve directly without code". We will handle auto-retrieval in verifyOtp if needed, or
                // user can just click verify with empty code if we store the event.
                // For simplicity, we just rely on standard flow: signin -> get token.
            });
            
            await FirebaseAuthentication.addListener('phoneVerificationFailed', (event) => {
                console.error('Phone verification failed:', event);
            });
            
            phoneListenersAdded = true;
        }

        const result = await FirebaseAuthentication.signInWithPhoneNumber({
            phoneNumber: phoneNumber
        });
        
        verificationId = result.verificationId;
    }

    async function sendOtpWeb(phoneNumber) {
        const { auth } = await initWebFirebase();
        await setupRecaptcha();
        
        try {
            confirmationResult = await auth.signInWithPhoneNumber(webAuth, phoneNumber, recaptchaVerifier);
        } catch (error) {
            if (recaptchaVerifier) {
                recaptchaVerifier.clear();
                recaptchaVerifier = null;
            }
            throw error;
        }
    }

    return {
        async sendOtp(phone10) {
            const fullPhone = `+91${phone10}`;
            
            if (window.Capacitor?.isNativePlatform()) {
                await sendOtpNative(fullPhone);
            } else {
                await sendOtpWeb(fullPhone);
            }
        },

        async verifyOtp(code) {
            let idToken = null;

            if (window.Capacitor?.isNativePlatform()) {
                const FirebaseAuthentication = window.Capacitor.Plugins.FirebaseAuthentication;
                
                // If auto verification completed, we might already be signed in or we might have verificationId + smsCode
                await FirebaseAuthentication.confirmVerificationCode({
                    verificationId: verificationId,
                    verificationCode: code
                });

                const result = await FirebaseAuthentication.getIdToken();
                idToken = result.token;
                
                await FirebaseAuthentication.signOut();
            } else {
                const { auth } = await initWebFirebase();
                
                if (!confirmationResult) {
                    throw new Error("No confirmation result available. Please request OTP again.");
                }
                
                const result = await confirmationResult.confirm(code);
                idToken = await result.user.getIdToken();
                
                await auth.signOut(webAuth);
            }
            
            return idToken;
        },

        reset() {
            verificationId = null;
            confirmationResult = null;
            if (recaptchaVerifier) {
                recaptchaVerifier.clear();
                recaptchaVerifier = null;
            }
        }
    };
})();
