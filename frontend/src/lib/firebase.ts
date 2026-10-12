import { getApp, getApps, initializeApp } from "firebase/app";
import { getAuth } from "firebase/auth";

const firebaseConfig = {
  apiKey: "AIzaSyDFe4RTiIlT2U39Auki_TtWY6KJglDZF_M",
  authDomain: "ai-invoice-d6b8a.firebaseapp.com",
  projectId: "ai-invoice-d6b8a",
  storageBucket: "ai-invoice-d6b8a.firebasestorage.app",
  messagingSenderId: "971533055874",
  appId: "1:971533055874:web:62d54494b42778a326419b",
  measurementId: "G-7K2TQWMVR9",
};

export const firebaseApp = getApps().length > 0 ? getApp() : initializeApp(firebaseConfig);
export const auth = getAuth(firebaseApp);
