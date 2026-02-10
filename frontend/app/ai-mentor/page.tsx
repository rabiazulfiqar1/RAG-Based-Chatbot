import Chat from "../components/chat";

export default function AiMentor() {
  return (
    <main className="relative min-h-screen bg-[#0d0d0d] p-6">
      {/* Logo and title in top-left */}
      <div className="relative flex items-center gap-3 mb-6">
        <div className="w-12 h-12 bg-white rounded-lg flex items-center justify-center">
          <span className="text-black font-bold text-2xl">D</span>
        </div>
        <h1 className="text-3xl font-bold text-white">
          DocuChat
        </h1>
      </div>

      {/* Chat container - full width with padding */}
      <Chat />
    </main>
  );
}
