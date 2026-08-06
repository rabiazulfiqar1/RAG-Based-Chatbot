"use client";
import { useEffect, useState } from "react";
import { useNavigation } from "@/app/components/navigation";
import { LoginModal } from "./components/login-modal";
import { supabase } from "@/lib/supabaseClient";
import type { User } from "@supabase/supabase-js";

export default function Component() {
  const { navigateToSignup, navigateToAIMentor } = useNavigation();
  const [isLoginModalOpen, setIsLoginModalOpen] = useState(false);
  const [user, setUser] = useState<User | null>(null);
  const [showProfileMenu, setShowProfileMenu] = useState(false);

  const openLoginModal = () => setIsLoginModalOpen(true);
  const closeLoginModal = () => setIsLoginModalOpen(false);

  useEffect(() => {
    const getUser = async () => {
      const {
        data: { session },
        error,
      } = await supabase.auth.getSession();

      if (error) {
        console.error("Error fetching session:", error.message);
        return;
      }

      if (session?.user) {
        setUser(session.user);
      } else {
        setUser(null);
      }
    };

    getUser();

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => {
      setUser(session?.user ?? null);
    });

    return () => {
      subscription.unsubscribe();
    };
  }, []);

  const handleSwitchToSignup = () => {
    closeLoginModal();
    navigateToSignup();
  };

  const handleLoginSuccess = () => {
    console.log("Login successful!");
  };

  const handleSignOut = async () => {
    await supabase.auth.signOut();
    setShowProfileMenu(false);
  };

  const getUserInitial = () => {
    if (user?.user_metadata?.name) {
      return user.user_metadata.name.charAt(0).toUpperCase();
    } else if (user?.email) {
      return user.email.charAt(0).toUpperCase();
    }
    return "U";
  };

  const getUserDisplayName = () => {
    return user?.user_metadata?.name || user?.email || "User";
  };

  return (
    <div className="min-h-screen bg-white">
      {/* Header */}
      <header className="fixed top-0 left-0 right-0 z-50 bg-white/80 backdrop-blur-md border-b border-gray-200">
        <div className="max-w-7xl mx-auto flex justify-between items-center p-4 lg:p-6">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-slate-900 rounded-lg flex items-center justify-center">
              <span className="text-white font-bold text-xl">D</span>
            </div>
            <p className="text-2xl lg:text-3xl font-bold text-slate-900">
              DocuChat
            </p>
          </div>

          <div className="flex gap-3 lg:gap-4">
            {user ? (
              <div className="relative">
                <button
                  onClick={() => setShowProfileMenu(!showProfileMenu)}
                  className="flex items-center gap-3 bg-gray-100 hover:bg-gray-200 border border-gray-300 rounded-full pl-2 pr-4 py-2 transition-all duration-300"
                >
                  <div className="bg-slate-900 text-white w-8 h-8 flex items-center justify-center rounded-full font-bold">
                    {getUserInitial()}
                  </div>
                  <span className="text-slate-900 font-medium hidden sm:block">{getUserDisplayName()}</span>
                  <svg 
                    className={`w-4 h-4 text-slate-900 transition-transform duration-200 ${showProfileMenu ? 'rotate-180' : ''}`} 
                    fill="none" 
                    stroke="currentColor" 
                    viewBox="0 0 24 24"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </button>

                {/* Profile Dropdown */}
                {showProfileMenu && (
                  <>
                    {/* Backdrop to close menu */}
                    <div 
                      className="fixed inset-0 z-40" 
                      onClick={() => setShowProfileMenu(false)}
                    />
                    
                    <div className="absolute right-0 mt-2 w-56 bg-white border border-gray-200 rounded-lg shadow-lg overflow-hidden z-50">
                      <div className="p-4 border-b border-gray-200">
                        <p className="text-slate-900 font-semibold truncate">{getUserDisplayName()}</p>
                        <p className="text-gray-600 text-sm truncate">{user.email}</p>
                      </div>
                      
                      <div className="p-2">
                        <button
                          onClick={navigateToAIMentor}
                          className="w-full flex items-center gap-3 px-4 py-3 text-left text-slate-900 hover:bg-gray-100 rounded-lg transition-colors"
                        >
                          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                          </svg>
                          Go to Chat
                        </button>
                        
                        <button
                          onClick={handleSignOut}
                          className="w-full flex items-center gap-3 px-4 py-3 text-left text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                        >
                          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
                          </svg>
                          Sign Out
                        </button>
                      </div>
                    </div>
                  </>
                )}
              </div>
            ) : (
              <>
                <button
                  onClick={openLoginModal}
                  className="bg-gray-100 hover:bg-gray-200 text-slate-900 border border-gray-300 rounded-full px-6 py-2.5 font-medium transition-all duration-300"
                >
                  Log In
                </button>
                <button
                  onClick={navigateToSignup}
                  className="bg-slate-900 hover:bg-slate-800 text-white rounded-full px-6 py-2.5 font-medium transition-all duration-300"
                >
                  Sign Up
                </button>
              </>
            )}
          </div>
        </div>
      </header>

      <main className="pt-20">
        {/* Hero Section */}
        <section className="max-w-7xl mx-auto px-6 py-20 lg:py-32">
          <div className="text-center max-w-4xl mx-auto">
            <div className="inline-block mb-6">
              <span className="bg-gray-100 text-slate-900 px-4 py-2 rounded-full text-sm font-medium border border-gray-300">
                AI-Powered Document Assistant
              </span>
            </div>
            
            <h1 className="text-5xl lg:text-7xl font-bold text-slate-900 leading-tight mb-6">
              Chat with Your
              <span className="text-slate-900"> Documents</span>
            </h1>
            
            <p className="text-xl lg:text-2xl text-gray-600 mb-10 leading-relaxed">
              Upload PDFs, Word docs, or paste URLs. Get instant answers with intelligent context-aware AI responses.
            </p>
            
            <div className="flex flex-col sm:flex-row gap-4 justify-center">
              <button
                onClick={() => {
                  if (!user) {
                    openLoginModal();
                    return;
                  }
                  navigateToAIMentor();
                }}
                className="bg-slate-900 hover:bg-slate-800 text-white rounded-full px-8 py-4 text-lg font-medium transition-all duration-300 hover:scale-105"
              >
                Start Chatting Now
              </button>
              <button
                onClick={() => document.getElementById('features')?.scrollIntoView({ behavior: 'smooth' })}
                className="bg-gray-100 hover:bg-gray-200 text-slate-900 border border-gray-300 rounded-full px-8 py-4 text-lg font-medium transition-all duration-300"
              >
                See How It Works
              </button>
            </div>
          </div>

          {/* Hero Image/Demo */}
          <div className="mt-20 relative">
            <div className="relative bg-gray-50 border border-gray-200 rounded-2xl p-6 shadow-sm">
              <div className="aspect-video bg-gray-100 rounded-lg flex items-center justify-center">
                <div className="text-center">
                  <div className="w-20 h-20 mx-auto mb-4 bg-slate-900 rounded-2xl flex items-center justify-center">
                    <svg className="w-10 h-10 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                    </svg>
                  </div>
                  <p className="text-gray-600 text-lg">Interactive chat interface preview</p>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Features Section */}
        <section id="features" className="py-20 lg:py-32 bg-gray-50">
          <div className="max-w-7xl mx-auto px-6">
            <div className="text-center mb-16">
              <h2 className="text-4xl lg:text-5xl font-bold text-slate-900 mb-6">
                Powerful Features for Smart Learning
              </h2>
              <p className="text-xl text-gray-600 max-w-2xl mx-auto">
                Everything you need to interact with your documents intelligently
              </p>
            </div>

            <div className="grid md:grid-cols-3 gap-8">
              {/* Feature 1 */}
              <div className="bg-white border border-gray-200 rounded-xl p-8 hover:border-gray-400 transition-all duration-300 shadow-sm">
                <div className="w-14 h-14 bg-slate-900 rounded-lg flex items-center justify-center mb-6">
                  <svg className="w-7 h-7 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                  </svg>
                </div>
                <h3 className="text-2xl font-bold text-slate-900 mb-4">Multi-Format Support</h3>
                <p className="text-gray-600 leading-relaxed">
                  Upload PDFs, Word documents, text files, or paste web URLs. We handle the rest.
                </p>
              </div>

              {/* Feature 2 */}
              <div className="bg-white border border-gray-200 rounded-xl p-8 hover:border-gray-400 transition-all duration-300 shadow-sm">
                <div className="w-14 h-14 bg-slate-900 rounded-lg flex items-center justify-center mb-6">
                  <svg className="w-7 h-7 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                  </svg>
                </div>
                <h3 className="text-2xl font-bold text-slate-900 mb-4">Lightning Fast</h3>
                <p className="text-gray-600 leading-relaxed">
                  Smart caching and streaming responses ensure you get answers instantly.
                </p>
              </div>

              {/* Feature 3 */}
              <div className="bg-white border border-gray-200 rounded-xl p-8 hover:border-gray-400 transition-all duration-300 shadow-sm">
                <div className="w-14 h-14 bg-slate-900 rounded-lg flex items-center justify-center mb-6">
                  <svg className="w-7 h-7 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                  </svg>
                </div>
                <h3 className="text-2xl font-bold text-slate-900 mb-4">Context-Aware AI</h3>
                <p className="text-gray-600 leading-relaxed">
                  Advanced RAG technology ensures answers are always relevant to your documents.
                </p>
              </div>
            </div>
          </div>
        </section>

        {/* How It Works */}
        <section className="py-20 lg:py-32 bg-white">
          <div className="max-w-7xl mx-auto px-6">
            <div className="text-center mb-16">
              <h2 className="text-4xl lg:text-5xl font-bold text-slate-900 mb-6">
                How It Works
              </h2>
              <p className="text-xl text-gray-600 max-w-2xl mx-auto">
                Three simple steps to start chatting with your documents
              </p>
            </div>

            <div className="grid md:grid-cols-3 gap-12">
              {/* Step 1 */}
              <div className="text-center">
                <div className="w-16 h-16 bg-slate-900 rounded-lg flex items-center justify-center mx-auto mb-6 text-white text-2xl font-bold">
                  1
                </div>
                <h3 className="text-2xl font-bold text-slate-900 mb-4">Upload</h3>
                <p className="text-gray-600 leading-relaxed">
                  Drop your PDF, Word doc, or paste a URL into the chat interface
                </p>
              </div>

              {/* Step 2 */}
              <div className="text-center">
                <div className="w-16 h-16 bg-slate-900 rounded-lg flex items-center justify-center mx-auto mb-6 text-white text-2xl font-bold">
                  2
                </div>
                <h3 className="text-2xl font-bold text-slate-900 mb-4">Ask</h3>
                <p className="text-gray-600 leading-relaxed">
                  Type your questions naturally - the AI understands context
                </p>
              </div>

              {/* Step 3 */}
              <div className="text-center">
                <div className="w-16 h-16 bg-slate-900 rounded-lg flex items-center justify-center mx-auto mb-6 text-white text-2xl font-bold">
                  3
                </div>
                <h3 className="text-2xl font-bold text-slate-900 mb-4">Learn</h3>
                <p className="text-gray-600 leading-relaxed">
                  Get instant, accurate answers with sources cited from your documents
                </p>
              </div>
            </div>
          </div>
        </section>

        {/* CTA Section */}
        <section className="py-20 bg-slate-900">
          <div className="max-w-4xl mx-auto text-center px-6">
            <h2 className="text-4xl lg:text-5xl font-bold text-white mb-6">
              Ready to Get Started?
            </h2>
            <p className="text-xl text-gray-300 mb-10">
              Join thousands of users who are learning smarter with AI-powered document chat
            </p>
            <button
              onClick={() => {
                if (!user) {
                  openLoginModal();
                  return;
                }
                navigateToAIMentor();
              }}
              className="bg-white hover:bg-gray-100 text-slate-900 rounded-full px-10 py-5 text-xl font-medium transition-all duration-300 hover:scale-105"
            >
              Start Free Today
            </button>
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer className="bg-white border-t border-gray-200 py-12">
        <div className="max-w-7xl mx-auto px-6 text-center">
          <div className="flex items-center justify-center gap-3 mb-4">
            <div className="w-10 h-10 bg-slate-900 rounded-lg flex items-center justify-center">
              <span className="text-white font-bold text-xl">D</span>
            </div>
            <p className="text-2xl font-bold text-slate-900">
              DocuChat
            </p>
          </div>
          <p className="text-gray-600">
            © 2026 DocuChat. Powered by AI. Built for learners.
          </p>
        </div>
      </footer>

      {/* Login Modal */}
      <LoginModal
        isOpen={isLoginModalOpen}
        onClose={closeLoginModal}
        onLoginClick={handleLoginSuccess}
        switchToSignup={handleSwitchToSignup}
      />
    </div>
  );
}
