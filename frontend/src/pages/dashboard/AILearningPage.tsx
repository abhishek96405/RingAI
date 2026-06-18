import { TrendingUp } from "lucide-react";
import { useAppSession } from "@/context/AppSessionContext";
import { isProPlan } from "@/lib/plan";
import AILearningWidget from "./AILearningWidget";

const AILearningPage = () => {
  const { activeRestaurant } = useAppSession();

  return (
    <div className="dash space-y-6">
      <div>
        <p className="eyebrow mb-2">Intelligence</p>
        <h1 className="text-2xl font-display font-bold">AI Learning</h1>
        <p className="text-sm text-ink-soft mt-1">
          Review and approve what the AI learns from your calls
        </p>
      </div>

      {isProPlan(activeRestaurant?.plan) ? (
        <AILearningWidget />
      ) : (
        <div className="dash-card p-6">
          <div className="text-center py-6">
            <div className="w-10 h-10 rounded-xl bg-coral/10 flex items-center justify-center mx-auto mb-3">
              <TrendingUp className="w-5 h-5 text-coral" />
            </div>
            <h4 className="font-display font-bold mb-1">AI Learning</h4>
            <p className="text-sm text-ink-soft mb-4">
              Auto-learn menu aliases and get AI improvement suggestions
            </p>
            <a href="/dashboard/billing" className="text-sm text-coral hover:underline font-medium">
              Upgrade to Pro →
            </a>
          </div>
        </div>
      )}
    </div>
  );
};

export default AILearningPage;
