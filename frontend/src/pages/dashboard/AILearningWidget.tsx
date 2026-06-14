import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Brain, CheckCircle, XCircle, AlertTriangle, Sparkles, Plus, RefreshCw } from "lucide-react";
import { api, getRestaurantId, approveLearningAlias, rejectLearningAlias } from "@/lib/api";
import { toast } from "sonner";

interface LearningStats {
  total_calls_processed: number;
  aliases_learned: number;
  calls_flagged: number;
  last_processed: string | null;
}

interface FlaggedCall {
  call_id: string;
  quality_score: number;
  issues: string[];
  order_accuracy: string;
  flagged_at: string;
  reviewed: boolean;
}

interface LearnedAlias {
  alias_term: string;
  target_item: string;
  occurrence_count: number;
  applied_at: string;
}

interface PendingSuggestion {
  id: string;
  alias_term?: string;
  target_item?: string;
  rule_text?: string;
  occurrence_count: number;
}

export const AILearningWidget = () => {
  const restaurantId = getRestaurantId() || "";
  
  const [stats, setStats] = useState<LearningStats | null>(null);
  const [flaggedCalls, setFlaggedCalls] = useState<FlaggedCall[]>([]);
  const [learnedAliases, setLearnedAliases] = useState<LearnedAlias[]>([]);
  const [pendingSuggestions, setPendingSuggestions] = useState<{
    pending_aliases: PendingSuggestion[];
    suggested_rules: PendingSuggestion[];
  }>({ pending_aliases: [], suggested_rules: [] });
  const [loading, setLoading] = useState(true);
  const [newAlias, setNewAlias] = useState("");
  const [newTarget, setNewTarget] = useState("");

  const fetchData = async () => {
    if (!restaurantId) return;
    
    try {
      setLoading(true);
      const [statsRes, flaggedRes, aliasesRes, suggestionsRes] = await Promise.all([
        api.get(`/restaurants/${restaurantId}/learning/stats`),
        api.get(`/restaurants/${restaurantId}/learning/flagged-calls?limit=5`),
        api.get(`/restaurants/${restaurantId}/learning/aliases`),
        api.get(`/restaurants/${restaurantId}/learning/suggestions`),
      ]);
      
      setStats(statsRes.data);
      setFlaggedCalls(flaggedRes.data.flagged_calls || []);
      setLearnedAliases(aliasesRes.data.aliases || []);
      setPendingSuggestions(suggestionsRes.data);
    } catch (err) {
      console.error("Failed to fetch learning data", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [restaurantId]);

  const handleReviewCall = async (callId: string, action: "correct" | "incorrect" | "ignore") => {
    try {
      await api.post(`/learning/flagged-calls/${callId}/review`, { action });
      toast.success(`Call marked as ${action}`);
      fetchData();
    } catch (err) {
      toast.error("Failed to submit review");
    }
  };

  const handleAddAlias = async () => {
    if (!newAlias || !newTarget) {
      toast.error("Enter both alias and target item");
      return;
    }
    
    try {
      await api.post(`/restaurants/${restaurantId}/learning/apply-alias`, null, {
        params: { alias: newAlias, target: newTarget },
      });
      toast.success(`Alias '${newAlias}' → '${newTarget}' added`);
      setNewAlias("");
      setNewTarget("");
      fetchData();
    } catch (err) {
      toast.error("Failed to add alias");
    }
  };

  const handleApproveAlias = async (aliasId: string) => {
    try {
      await approveLearningAlias(restaurantId, aliasId);
      toast.success("Alias approved and added to your menu");
      fetchData();
    } catch (err) {
      toast.error("Failed to approve alias");
    }
  };

  const handleRejectAlias = async (aliasId: string) => {
    try {
      await rejectLearningAlias(restaurantId, aliasId);
      toast.success("Suggestion dismissed");
      fetchData();
    } catch (err) {
      toast.error("Failed to dismiss suggestion");
    }
  };

  if (loading) {
    return (
      <Card className="p-6">
        <div className="flex items-center justify-center h-32 text-muted-foreground">
          <RefreshCw className="w-5 h-5 animate-spin mr-2" /> Loading AI Learning...
        </div>
      </Card>
    );
  }

  return (
    <div className="space-y-4" data-testid="ai-learning-widget">
      {/* Stats Overview */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Brain className="w-5 h-5 text-primary" />
              <CardTitle className="text-lg">AI Auto-Learning</CardTitle>
            </div>
            <Button variant="ghost" size="sm" onClick={fetchData}>
              <RefreshCw className="w-4 h-4" />
            </Button>
          </div>
          <CardDescription>
            The AI suggests aliases from your calls - you approve what goes live
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-3 gap-4 text-center">
            <div className="p-3 rounded-lg bg-muted/50">
              <div className="text-2xl font-bold text-primary">{stats?.total_calls_processed || 0}</div>
              <div className="text-xs text-muted-foreground">Calls Processed</div>
            </div>
            <div className="p-3 rounded-lg bg-muted/50">
              <div className="text-2xl font-bold text-green-600">{stats?.aliases_learned || 0}</div>
              <div className="text-xs text-muted-foreground">Aliases Learned</div>
            </div>
            <div className="p-3 rounded-lg bg-muted/50">
              <div className="text-2xl font-bold text-orange-500">{stats?.calls_flagged || 0}</div>
              <div className="text-xs text-muted-foreground">Needs Review</div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Flagged Calls - Exception Only Review */}
      {flaggedCalls.length > 0 && (
        <Card className="border-orange-200">
          <CardHeader className="pb-2">
            <CardTitle className="text-base flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-orange-500" />
              Calls Needing Review ({flaggedCalls.length})
            </CardTitle>
            <CardDescription>
              Only low-quality calls are flagged - quick 1-click review
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {flaggedCalls.slice(0, 3).map((call) => (
              <div
                key={call.call_id}
                className="p-3 rounded-lg border bg-card flex items-center justify-between"
                data-testid={`flagged-call-${call.call_id}`}
              >
                <div>
                  <div className="flex items-center gap-2">
                    <Badge variant="secondary" className="bg-orange-100 text-orange-700">
                      Score: {call.quality_score}
                    </Badge>
                    <span className="text-xs text-muted-foreground">
                      {new Date(call.flagged_at).toLocaleDateString()}
                    </span>
                  </div>
                  {call.issues.length > 0 && (
                    <p className="text-xs text-muted-foreground mt-1 truncate max-w-[250px]">
                      {call.issues[0]}
                    </p>
                  )}
                </div>
                <div className="flex gap-1">
                  <Button
                    size="sm"
                    variant="ghost"
                    className="text-green-600 hover:text-green-700 hover:bg-green-50"
                    onClick={() => handleReviewCall(call.call_id, "correct")}
                    title="AI was correct"
                  >
                    <CheckCircle className="w-4 h-4" />
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="text-red-600 hover:text-red-700 hover:bg-red-50"
                    onClick={() => handleReviewCall(call.call_id, "incorrect")}
                    title="AI made a mistake"
                  >
                    <XCircle className="w-4 h-4" />
                  </Button>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {/* Learned Aliases */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-primary" />
            Auto-Learned Aliases
          </CardTitle>
          <CardDescription>
            The AI learns what customers call your menu items
          </CardDescription>
        </CardHeader>
        <CardContent>
          {learnedAliases.length > 0 ? (
            <div className="flex flex-wrap gap-2 mb-4">
              {learnedAliases.slice(0, 8).map((alias, i) => (
                <Badge key={i} variant="outline" className="py-1">
                  "{alias.alias_term}" → {alias.target_item}
                </Badge>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground mb-4">
              No aliases learned yet. They'll appear automatically as customers order.
            </p>
          )}
          
          {/* Pending suggestions — approve/reject (C24-1) */}
          {pendingSuggestions.pending_aliases.length > 0 && (
            <div className="mb-4">
              <p className="text-xs text-muted-foreground mb-2">
                Pending review ({pendingSuggestions.pending_aliases.length}) - approve to add to your menu
              </p>
              <div className="space-y-2">
                {pendingSuggestions.pending_aliases.slice(0, 8).map((s) => (
                  <div
                    key={s.id}
                    className="flex items-center justify-between gap-2 p-2 rounded-lg border bg-card"
                    data-testid={`pending-alias-${s.id}`}
                  >
                    <div className="min-w-0 text-sm">
                      <span className="font-medium">"{s.alias_term}"</span>
                      <span className="text-muted-foreground"> → {s.target_item}</span>
                      <Badge variant="secondary" className="text-xs ml-2">{s.occurrence_count}x</Badge>
                    </div>
                    <div className="flex gap-1 shrink-0">
                      <Button
                        size="sm"
                        variant="ghost"
                        className="text-green-600 hover:text-green-700 hover:bg-green-50"
                        onClick={() => handleApproveAlias(s.id)}
                        title="Approve - add this alias to your menu"
                      >
                        <CheckCircle className="w-4 h-4" />
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        className="text-red-600 hover:text-red-700 hover:bg-red-50"
                        onClick={() => handleRejectAlias(s.id)}
                        title="Reject - dismiss this suggestion"
                      >
                        <XCircle className="w-4 h-4" />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
          
          {/* Manual alias add */}
          <div className="flex gap-2 items-end">
            <div className="flex-1">
              <Input
                placeholder="Alias (e.g., 'coke')"
                value={newAlias}
                onChange={(e) => setNewAlias(e.target.value)}
                className="h-9 text-sm"
              />
            </div>
            <div className="flex-1">
              <Input
                placeholder="Menu item (e.g., 'Coca-Cola')"
                value={newTarget}
                onChange={(e) => setNewTarget(e.target.value)}
                className="h-9 text-sm"
              />
            </div>
            <Button size="sm" onClick={handleAddAlias} className="h-9">
              <Plus className="w-4 h-4" />
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Suggested Rules */}
      {pendingSuggestions.suggested_rules.length > 0 && (
        <Card className="border-blue-200">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Suggested Improvements</CardTitle>
            <CardDescription>
              Based on call patterns, the AI suggests these rules
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2 text-sm">
              {pendingSuggestions.suggested_rules.slice(0, 3).map((rule, i) => (
                <li key={i} className="flex items-start gap-2">
                  <span className="text-primary">•</span>
                  <span>{rule.rule_text}</span>
                  <Badge variant="secondary" className="text-xs ml-auto">
                    {rule.occurrence_count}x
                  </Badge>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default AILearningWidget;
