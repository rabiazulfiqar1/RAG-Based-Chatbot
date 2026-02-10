"use client"

import { useRouter } from "next/navigation";

export const useNavigation = () => {
  const router = useRouter();

  return {
    navigateToSignup: () => router.push("/signup"),
    navigateToHome: () => router.push("/"),
    navigateToMindmaps: () => router.push("/mindmaps"),
    navigateToChat: () => router.push("/chat"),
    navigateToAIMentor: () => router.push("/ai-mentor"),
    navigateToGetStarted: () => router.push("/get-started"),
    navigateToFeatures: () => {
      const section = document.getElementById("features");
      section?.scrollIntoView({ behavior: "smooth" });
    },
  };
};

