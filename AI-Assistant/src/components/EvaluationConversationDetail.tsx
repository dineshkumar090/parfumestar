import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
    Page, Layout, Card, Text, BlockStack, InlineStack,
    Badge, Spinner, Banner, Button, Divider, Tooltip
} from '@shopify/polaris';
import {
    MonitorIcon, SmartphoneIcon, MailIcon, ClockIcon,
    MessageCircleIcon, CheckCircleIcon, CircleIcon,
    ZapIcon, BarChart3Icon, RefreshCwIcon, AwardIcon,
    StarIcon, AlertTriangleIcon
} from 'lucide-react';

interface EvaluationScores {
    answer_relevancy: number;
    context_relevancy: number;
    faithfulness: number;
    answer_correctness?: number;
}

// Add this to your MessageBubble component props
interface MessageBubbleProps {
    msg: ChatMessage;
    onEvaluate: (id: number) => void;
    evaluating: boolean;
    isEvaluating: boolean;
    onSubmitFeedback?: (messageId: number, rating: string, customResponse?: string) => void;
}

interface MessageEvaluation {
    scores: EvaluationScores;
    avg_score: number;
    evaluated_at?: string;
    contexts_used?: string[];
}

interface ChatMessage {
    id: number;
    role: 'user' | 'assistant';
    content: string;
    response_data: any;
    latency_ms: number | null;
    timestamp: string | null;
    evaluation?: MessageEvaluation;
}

const PYTHON_API_URL = import.meta.env.VITE_PYTHON_API_URL;

function ScoreBadge({ score, label, size = 'small' }: { score: number; label: string; size?: 'small' | 'large' }) {
    const getColor = () => {
        if (score >= 0.9) return '#008060';
        if (score >= 0.7) return '#5c6ac4';
        if (score >= 0.5) return '#ffc453';
        return '#d72c0d';
    };

    const getIcon = () => {
        if (score >= 0.9) return <AwardIcon size={12} color="#008060" />;
        if (score >= 0.7) return <StarIcon size={12} color="#5c6ac4" />;
        return <AlertTriangleIcon size={12} color={getColor()} />;
    };

    if (size === 'large') {
        return (
            <div style={{ textAlign: 'center' }}>
                <div style={{
                    width: 60, height: 60, borderRadius: 30,
                    background: `${getColor()}15`,
                    border: `2px solid ${getColor()}`,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    marginBottom: 8
                }}>
                    <Text as="p" variant="headingMd" style={{ color: getColor() }}>
                        {(score * 100).toFixed(0)}%
                    </Text>
                </div>
                <Text as="p" variant="bodySm" tone="subdued">{label}</Text>
            </div>
        );
    }

    return (
        <Tooltip content={`${label}: ${(score * 100).toFixed(0)}%`}>
            <div style={{
                display: 'inline-flex', alignItems: 'center', gap: 4,
                padding: '2px 8px', borderRadius: 12,
                background: `${getColor()}15`, border: `1px solid ${getColor()}30`
            }}>
                {getIcon()}
                <Text as="span" variant="bodySm" fontWeight="semibold" style={{ color: getColor() }}>
                    {(score * 100).toFixed(0)}%
                </Text>
            </div>
        </Tooltip>
    );
}

function MessageBubble({ msg, onEvaluate, evaluating, isEvaluating, onSubmitFeedback }: {
    msg: ChatMessage;
    onEvaluate: (id: number) => void;
    evaluating: boolean;
    isEvaluating: boolean;
    onSubmitFeedback: (messageId: number, rating: string, customResponse?: string) => void;
}) {
    const isUser = msg.role === 'user';
    const hasEvaluation = !!msg.evaluation;
    const [showFeedback, setShowFeedback] = useState(false);
    const [rating, setRating] = useState('');
    const [customResponse, setCustomResponse] = useState('');

    return (
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: isUser ? 'flex-end' : 'flex-start', gap: 6 }}>
            <InlineStack gap="200" blockAlign="center">
                <Text as="p" variant="bodySm" tone="subdued">
                    {isUser ? '👤 Customer' : '🤖 AI Assistant'}
                    {msg.timestamp && ` · ${new Date(msg.timestamp).toLocaleString()}`}
                </Text>
                {!isUser && msg.latency_ms && (
                    <Badge tone="info">{msg.latency_ms}ms</Badge>
                )}
            </InlineStack>

            {/* Evaluation Button */}
            {!isUser && (
                <div style={{ marginBottom: 4 }}>
                    <Button
                        variant={hasEvaluation ? "plain" : "primary"}
                        size="slim"
                        loading={isEvaluating}
                        onClick={() => onEvaluate(msg.id)}
                        icon={() => <BarChart3Icon size={14} />}
                    >
                        {hasEvaluation ? 'Re-evaluate' : 'Evaluate Message'}
                    </Button>
                </div>
            )}

            <div style={{
                maxWidth: '70%', padding: '10px 14px',
                borderRadius: isUser ? '18px 4px 18px 18px' : '4px 18px 18px 18px',
                background: isUser ? '#2d6a4f' : '#fff',
                color: isUser ? '#fff' : '#1a2e1a',
                border: isUser ? 'none' : '1px solid #d0e8da',
            }}>
                <Text as="p" variant="bodyMd">{msg.content}</Text>
            </div>

            {/* Show Evaluation Scores and Suggestion */}
            {!isUser && hasEvaluation && msg.evaluation && (
                <>
                    <div style={{
                        background: '#f8f9fa', padding: '8px 12px', borderRadius: 8,
                        display: 'flex', gap: 12, flexWrap: 'wrap', border: '1px solid #e1e3e5'
                    }}>
                        <ScoreBadge score={msg.evaluation.scores.answer_relevancy} label="Answer" />
                        <ScoreBadge score={msg.evaluation.scores.context_relevancy} label="Context" />
                        <ScoreBadge score={msg.evaluation.scores.faithfulness} label="Faithful" />
                        <div style={{ borderLeft: '1px solid #e1e3e5', paddingLeft: 8 }}>
                            <ScoreBadge score={msg.evaluation.avg_score} label="Overall" />
                        </div>
                    </div>

                    {/* Suggested Better Response */}
                    {msg.evaluation.suggested_response && (
                        <div style={{
                            background: '#e6f7e6',
                            padding: '10px 12px',
                            borderRadius: 8,
                            border: '1px solid #b3e0b3',
                            maxWidth: '90%'
                        }}>
                            <InlineStack gap="100" blockAlign="center">
                                <ZapIcon size={14} color="#008060" />
                                <Text as="p" variant="bodySm" fontWeight="semibold" style={{ color: '#008060' }}>
                                    Suggested Better Response:
                                </Text>
                            </InlineStack>
                            <Text as="p" variant="bodyMd" style={{ marginTop: 6, color: '#1a2e1a' }}>
                                {msg.evaluation.suggested_response}
                            </Text>


                        </div>
                    )}

                    {/* Custom Feedback Form */}
                    {showFeedback && (
                        <div style={{
                            background: '#f0f7ff',
                            padding: '12px',
                            borderRadius: 8,
                            border: '1px solid #c4e0ff',
                            width: '100%',
                            maxWidth: '500px'
                        }}>
                            <Text as="h3" variant="headingSm" style={{ marginBottom: 8 }}>
                                Suggest a different response:
                            </Text>

                            <textarea
                                value={customResponse}
                                onChange={(e) => setCustomResponse(e.target.value)}
                                placeholder="What should the assistant have said instead?"
                                style={{
                                    width: '100%',
                                    minHeight: '80px',
                                    padding: '8px',
                                    borderRadius: '4px',
                                    border: '1px solid #c9cccf',
                                    fontSize: '14px',
                                    fontFamily: 'inherit',
                                    resize: 'vertical'
                                }}
                            />

                            <InlineStack gap="200" style={{ marginTop: 8 }}>
                                <Button
                                    variant="primary"
                                    onClick={() => {
                                        if (customResponse.trim()) {
                                            onSubmitFeedback(msg.id, 'custom', customResponse);
                                            setShowFeedback(false);
                                            setCustomResponse('');
                                        }
                                    }}
                                    disabled={!customResponse.trim()}
                                >
                                    Submit Custom Response
                                </Button>
                                <Button onClick={() => setShowFeedback(false)}>Cancel</Button>
                            </InlineStack>
                        </div>
                    )}
                </>
            )}

            {/* Message Content */}


            {/* Contexts */}
            {!isUser && hasEvaluation && msg.evaluation?.contexts_used && msg.evaluation.contexts_used.length > 0 && (
                <details style={{ maxWidth: '70%' }}>
                    <summary style={{ cursor: 'pointer', color: '#6d7175', fontSize: 12 }}>
                        📚 Context used ({msg.evaluation.contexts_used.length})
                    </summary>
                    <div style={{ marginTop: 8, fontSize: 11, background: '#f6f6f7', padding: 8, borderRadius: 6 }}>
                        {msg.evaluation.contexts_used.map((ctx, idx) => (
                            <div key={idx} style={{ marginBottom: 4, padding: 4, background: '#fff', borderRadius: 4 }}>
                                {ctx}
                            </div>
                        ))}
                    </div>
                </details>
            )}
        </div>
    );
}
export default function EvaluationConversationDetail() {
    const { threadUuid } = useParams();
    const navigate = useNavigate();

    const [conversation, setConversation] = useState<any>(null);
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [evaluationSummary, setEvaluationSummary] = useState<any>(null);
    const [loading, setLoading] = useState(true);
    const [evaluating, setEvaluating] = useState(false);
    const [selectedMessageId, setSelectedMessageId] = useState<number | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [refreshTrigger, setRefreshTrigger] = useState(0);

    const fetchConversation = async () => {
        setLoading(true);
        try {
            const response = await fetch(`${PYTHON_API_URL}/api/evaluation/conversation/${threadUuid}`);
            if (!response.ok) throw new Error('Failed to load conversation');
            const data = await response.json();
            setConversation(data.thread);

            // Parse messages with evaluations from response_data
            const parsedMessages = data.messages.map((msg: any) => {
                const hasEvaluation = msg.response_data?.ragas_scores;
                if (hasEvaluation && msg.role === 'assistant') {
                    const scores = msg.response_data.ragas_scores;
                    const scoreValues = Object.values(scores) as number[];
                    const avgScore = scoreValues.reduce((a, b) => a + b, 0) / scoreValues.length;

                    if (msg.evaluation) {
                        return {
                            ...msg,
                            evaluation: {
                                scores: msg.evaluation.scores,
                                avg_score: msg.evaluation.avg_score,
                                evaluated_at: msg.evaluation.evaluated_at,
                                contexts_used: msg.evaluation.contexts_used || []
                            }
                        };
                    }
                }
                return msg;
            });

            setMessages(parsedMessages);
            setEvaluationSummary(data.evaluation_summary);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to load');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        if (threadUuid) fetchConversation();
    }, [threadUuid, refreshTrigger]);

    const evaluateMessage = async (messageId: number) => {
        setEvaluating(true);
        setSelectedMessageId(messageId);
        setError(null);

        try {
            const response = await fetch(`${PYTHON_API_URL}/api/evaluation/evaluate/message/${messageId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });

            const result = await response.json();

            if (response.ok && !result.error) {
                // Refresh to show new evaluation
                setRefreshTrigger(prev => prev + 1);
            } else {
                setError(result.error || 'Evaluation failed');
                console.error('Evaluation error:', result);
            }
        } catch (err) {
            setError('Failed to evaluate message');
            console.error(err);
        } finally {
            setEvaluating(false);
            setSelectedMessageId(null);
        }
    };


    const onSubmitFeedback = async (messageId: number, rating: string, customResponse?: string) => {
        try {
            const response = await fetch(`${PYTHON_API_URL}/api/evaluation/feedback/${messageId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    rating: rating,
                    custom_suggested_response: customResponse
                })
            });

            if (response.ok) {
                // Refresh to show updated feedback
                setRefreshTrigger(prev => prev + 1);
            }
        } catch (err) {
            console.error('Failed to submit feedback:', err);
        }
    };

    // Helper functions for evaluation summary with soft colors
    const getScoreColor = (score: number): string => {
        if (score >= 0.9) return '#2d6a4f';  // Deep green
        if (score >= 0.7) return '#5c6ac4';  // Soft blue
        if (score >= 0.5) return '#e6a017';  // Muted orange
        return '#c94f4f';  // Soft red
    };

    const getOverallScoreColor = (score: number): string => {
        if (score >= 0.9) return '#1b5e20';
        if (score >= 0.8) return '#2e7d32';
        if (score >= 0.7) return '#5c6ac4';
        if (score >= 0.6) return '#e6a017';
        if (score >= 0.5) return '#f57c00';
        return '#c94f4f';
    };

    const getScoreRating = (score: number): string => {
        if (score >= 0.9) return 'Excellent';
        if (score >= 0.7) return 'Good';
        if (score >= 0.5) return 'Fair';
        return 'Needs Work';
    };

    const getOverallGrade = (score: number): string => {
        if (score >= 0.9) return 'A';
        if (score >= 0.8) return 'B';
        if (score >= 0.7) return 'C';
        if (score >= 0.6) return 'D';
        if (score >= 0.5) return 'E';
        return 'F';
    };

    const getInsightMessage = (summary: any): string => {
        const overall = summary.overall_avg || 0;
        const answerRel = summary.avg_scores?.answer_relevancy || 0;
        const faithfulness = summary.avg_scores?.faithfulness || 0;

        if (overall >= 0.8) {
            return 'Excellent performance! Your AI assistant is providing high-quality responses consistently.';
        } else if (overall >= 0.6) {
            if (answerRel < 0.7) {
                return 'Good overall, but answer relevancy needs improvement. Focus on providing more direct answers to user questions.';
            } else if (faithfulness < 0.7) {
                return 'Good overall, but watch for hallucinations. Ensure responses are faithful to the provided context.';
            }
            return 'Decent performance with room for improvement. Review suggested improvements for better results.';
        } else {
            return 'Needs significant improvement. Consider reviewing response patterns and updating your knowledge base.';
        }
    };

    if (loading) {
        return (
            <Page title="Evaluation">
                <div style={{ textAlign: 'center', padding: 80 }}>
                    <Spinner size="large" />
                </div>
            </Page>
        );
    }

    if (error || !conversation) {
        return (
            <Page title="Evaluation">
                <Banner tone="critical">{error || 'Conversation not found'}</Banner>
                <div style={{ marginTop: 16 }}>
                    <Button onClick={() => navigate('/evaluation')}>Back to Dashboard</Button>
                </div>
            </Page>
        );
    }

    const assistantMessages = messages.filter(m => m.role === 'assistant');
    const evaluatedCount = assistantMessages.filter(m => m.evaluation).length;

    return (
        <Page
            title={`Evaluation: ${conversation.thread_uuid?.slice(-8) || 'Conversation'}`}
            subtitle={`${evaluatedCount}/${assistantMessages.length} messages evaluated`}
            backAction={{ content: 'Dashboard', onAction: () => navigate('/evaluation') }}
            primaryAction={{
                content: 'Refresh',
                onAction: fetchConversation,
                icon: () => <RefreshCwIcon size={16} />
            }}
        >
            <Layout>
                {/* Evaluation Summary */}
                <Layout.Section>
                    <Card>
                        <BlockStack gap="300">
                            <InlineStack align="space-between" blockAlign="center">
                                <Text as="h2" variant="headingMd">Evaluation Summary</Text>
                                {evaluationSummary?.total_evaluations > 0 && (
                                    <Badge tone="success" size="medium">
                                        {evaluationSummary.total_evaluations} Evaluated Messages
                                    </Badge>
                                )}
                            </InlineStack>
                            <Divider />

                            {evaluationSummary?.total_evaluations > 0 ? (
                                <>
                                    {/* Metric Cards with Soft Colors */}
                                    <div style={{
                                        display: 'grid',
                                        gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
                                        gap: 16
                                    }}>
                                        {/* Answer Relevancy Card */}
                                        <div style={{
                                            background: '#f0f4f8',
                                            borderRadius: 12,
                                            padding: 20,
                                            position: 'relative',
                                            transition: 'transform 0.2s ease, box-shadow 0.2s ease',
                                            cursor: 'pointer',
                                            border: '1px solid #e1e8ed',
                                        }}
                                            onMouseEnter={(e) => {
                                                e.currentTarget.style.transform = 'translateY(-2px)';
                                                e.currentTarget.style.boxShadow = '0 4px 12px rgba(0,0,0,0.08)';
                                            }}
                                            onMouseLeave={(e) => {
                                                e.currentTarget.style.transform = 'translateY(0)';
                                                e.currentTarget.style.boxShadow = 'none';
                                            }}>
                                            <div>
                                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                                                    <Text as="p" variant="bodyMd" fontWeight="semibold" style={{ color: '#1a2e1a' }}>
                                                        Answer Relevancy
                                                    </Text>
                                                    <div style={{
                                                        background: '#e8f0e8',
                                                        borderRadius: 12,
                                                        padding: '4px 8px',
                                                        fontSize: 11,
                                                        color: '#2d6a4f',
                                                    }}>
                                                        Direct answers
                                                    </div>
                                                </div>
                                                <Text as="p" variant="heading2xl" fontWeight="bold" style={{ color: '#1a2e1a', marginBottom: 12 }}>
                                                    {(evaluationSummary.avg_scores?.answer_relevancy * 100).toFixed(0)}%
                                                </Text>
                                                <div style={{
                                                    width: '100%',
                                                    height: 6,
                                                    background: '#e1e8ed',
                                                    borderRadius: 3,
                                                    overflow: 'hidden',
                                                    marginBottom: 12,
                                                }}>
                                                    <div style={{
                                                        width: `${(evaluationSummary.avg_scores?.answer_relevancy || 0) * 100}%`,
                                                        height: '100%',
                                                        background: getScoreColor(evaluationSummary.avg_scores?.answer_relevancy || 0),
                                                        borderRadius: 3,
                                                        transition: 'width 0.3s ease',
                                                    }} />
                                                </div>
                                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                                    <Text as="p" variant="bodySm" tone="subdued">
                                                        Score
                                                    </Text>
                                                    <div style={{
                                                        background: '#f5f5f5',
                                                        borderRadius: 16,
                                                        padding: '4px 12px',
                                                        fontSize: 12,
                                                        fontWeight: 500,
                                                        color: getScoreColor(evaluationSummary.avg_scores?.answer_relevancy || 0),
                                                    }}>
                                                        {getScoreRating(evaluationSummary.avg_scores?.answer_relevancy || 0)}
                                                    </div>
                                                </div>
                                            </div>
                                        </div>

                                        {/* Context Relevancy Card */}
                                        <div style={{
                                            background: '#f8f4f0',
                                            borderRadius: 12,
                                            padding: 20,
                                            transition: 'transform 0.2s ease, box-shadow 0.2s ease',
                                            cursor: 'pointer',
                                            border: '1px solid #e8e0d8',
                                        }}
                                            onMouseEnter={(e) => {
                                                e.currentTarget.style.transform = 'translateY(-2px)';
                                                e.currentTarget.style.boxShadow = '0 4px 12px rgba(0,0,0,0.08)';
                                            }}
                                            onMouseLeave={(e) => {
                                                e.currentTarget.style.transform = 'translateY(0)';
                                                e.currentTarget.style.boxShadow = 'none';
                                            }}>
                                            <div>
                                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                                                    <Text as="p" variant="bodyMd" fontWeight="semibold" style={{ color: '#4a3728' }}>
                                                        Context Relevancy
                                                    </Text>
                                                    <div style={{
                                                        background: '#f0e8e0',
                                                        borderRadius: 12,
                                                        padding: '4px 8px',
                                                        fontSize: 11,
                                                        color: '#8b5a2b',
                                                    }}>
                                                        Context usage
                                                    </div>
                                                </div>
                                                <Text as="p" variant="heading2xl" fontWeight="bold" style={{ color: '#4a3728', marginBottom: 12 }}>
                                                    {(evaluationSummary.avg_scores?.context_relevancy * 100).toFixed(0)}%
                                                </Text>
                                                <div style={{
                                                    width: '100%',
                                                    height: 6,
                                                    background: '#e8e0d8',
                                                    borderRadius: 3,
                                                    overflow: 'hidden',
                                                    marginBottom: 12,
                                                }}>
                                                    <div style={{
                                                        width: `${(evaluationSummary.avg_scores?.context_relevancy || 0) * 100}%`,
                                                        height: '100%',
                                                        background: getScoreColor(evaluationSummary.avg_scores?.context_relevancy || 0),
                                                        borderRadius: 3,
                                                        transition: 'width 0.3s ease',
                                                    }} />
                                                </div>
                                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                                    <Text as="p" variant="bodySm" tone="subdued">
                                                        Score
                                                    </Text>
                                                    <div style={{
                                                        background: '#f5f2ef',
                                                        borderRadius: 16,
                                                        padding: '4px 12px',
                                                        fontSize: 12,
                                                        fontWeight: 500,
                                                        color: getScoreColor(evaluationSummary.avg_scores?.context_relevancy || 0),
                                                    }}>
                                                        {getScoreRating(evaluationSummary.avg_scores?.context_relevancy || 0)}
                                                    </div>
                                                </div>
                                            </div>
                                        </div>

                                        {/* Faithfulness Card */}
                                        <div style={{
                                            background: '#f0f4f0',
                                            borderRadius: 12,
                                            padding: 20,
                                            transition: 'transform 0.2s ease, box-shadow 0.2s ease',
                                            cursor: 'pointer',
                                            border: '1px solid #d8e0d8',
                                        }}
                                            onMouseEnter={(e) => {
                                                e.currentTarget.style.transform = 'translateY(-2px)';
                                                e.currentTarget.style.boxShadow = '0 4px 12px rgba(0,0,0,0.08)';
                                            }}
                                            onMouseLeave={(e) => {
                                                e.currentTarget.style.transform = 'translateY(0)';
                                                e.currentTarget.style.boxShadow = 'none';
                                            }}>
                                            <div>
                                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                                                    <Text as="p" variant="bodyMd" fontWeight="semibold" style={{ color: '#2a4a2a' }}>
                                                        Faithfulness
                                                    </Text>
                                                    <div style={{
                                                        background: '#e0e8e0',
                                                        borderRadius: 12,
                                                        padding: '4px 8px',
                                                        fontSize: 11,
                                                        color: '#4a6a4a',
                                                    }}>
                                                        No hallucinations
                                                    </div>
                                                </div>
                                                <Text as="p" variant="heading2xl" fontWeight="bold" style={{ color: '#2a4a2a', marginBottom: 12 }}>
                                                    {(evaluationSummary.avg_scores?.faithfulness * 100).toFixed(0)}%
                                                </Text>
                                                <div style={{
                                                    width: '100%',
                                                    height: 6,
                                                    background: '#d8e0d8',
                                                    borderRadius: 3,
                                                    overflow: 'hidden',
                                                    marginBottom: 12,
                                                }}>
                                                    <div style={{
                                                        width: `${(evaluationSummary.avg_scores?.faithfulness || 0) * 100}%`,
                                                        height: '100%',
                                                        background: getScoreColor(evaluationSummary.avg_scores?.faithfulness || 0),
                                                        borderRadius: 3,
                                                        transition: 'width 0.3s ease',
                                                    }} />
                                                </div>
                                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                                    <Text as="p" variant="bodySm" tone="subdued">
                                                        Score
                                                    </Text>
                                                    <div style={{
                                                        background: '#eef2ee',
                                                        borderRadius: 16,
                                                        padding: '4px 12px',
                                                        fontSize: 12,
                                                        fontWeight: 500,
                                                        color: getScoreColor(evaluationSummary.avg_scores?.faithfulness || 0),
                                                    }}>
                                                        {getScoreRating(evaluationSummary.avg_scores?.faithfulness || 0)}
                                                    </div>
                                                </div>
                                            </div>
                                        </div>

                                        {/* Overall Score Card */}
                                        <div style={{
                                            background: '#eef2f4',
                                            borderRadius: 12,
                                            padding: 20,
                                            transition: 'transform 0.2s ease, box-shadow 0.2s ease',
                                            cursor: 'pointer',
                                            border: '2px solid #d0dce4',
                                        }}
                                            onMouseEnter={(e) => {
                                                e.currentTarget.style.transform = 'translateY(-2px)';
                                                e.currentTarget.style.boxShadow = '0 4px 12px rgba(0,0,0,0.08)';
                                            }}
                                            onMouseLeave={(e) => {
                                                e.currentTarget.style.transform = 'translateY(0)';
                                                e.currentTarget.style.boxShadow = 'none';
                                            }}>
                                            <div>
                                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                                                    <Text as="p" variant="bodyMd" fontWeight="semibold" style={{ color: '#1a3a4a' }}>
                                                        Overall Performance
                                                    </Text>
                                                    <div style={{
                                                        background: '#dce4e8',
                                                        borderRadius: 16,
                                                        padding: '4px 12px',
                                                        fontSize: 12,
                                                        fontWeight: 600,
                                                        color: getOverallScoreColor(evaluationSummary.overall_avg || 0),
                                                    }}>
                                                        {getOverallGrade(evaluationSummary.overall_avg || 0)}
                                                    </div>
                                                </div>
                                                <Text as="p" variant="heading2xl" fontWeight="bold" style={{ color: '#1a3a4a', marginBottom: 12 }}>
                                                    {(evaluationSummary.overall_avg * 100).toFixed(0)}%
                                                </Text>
                                                <div style={{
                                                    width: '100%',
                                                    height: 6,
                                                    background: '#dce4e8',
                                                    borderRadius: 3,
                                                    overflow: 'hidden',
                                                    marginBottom: 12,
                                                }}>
                                                    <div style={{
                                                        width: `${(evaluationSummary.overall_avg || 0) * 100}%`,
                                                        height: '100%',
                                                        background: getScoreColor(evaluationSummary.overall_avg || 0),
                                                        borderRadius: 3,
                                                        transition: 'width 0.3s ease',
                                                    }} />
                                                </div>
                                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                                    <Text as="p" variant="bodySm" tone="subdued">
                                                        Quality Score
                                                    </Text>
                                                    <div style={{
                                                        background: '#e8eef0',
                                                        borderRadius: 16,
                                                        padding: '4px 12px',
                                                        fontSize: 12,
                                                        fontWeight: 600,
                                                    }}>
                                                        {getScoreRating(evaluationSummary.overall_avg || 0)}
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    </div>

                                    {/* Additional Insights */}
                                    <div style={{
                                        background: '#f7f8f9',
                                        borderRadius: 12,
                                        padding: 16,
                                        marginTop: 8,
                                        border: '1px solid #e8ecef',
                                    }}>
                                        <InlineStack gap="200" blockAlign="center">
                                            <div style={{
                                                width: 32,
                                                height: 32,
                                                borderRadius: 8,
                                                background: '#e8f0f7',
                                                display: 'flex',
                                                alignItems: 'center',
                                                justifyContent: 'center',
                                            }}>
                                                <span style={{ fontSize: 16 }}>💡</span>
                                            </div>
                                            <BlockStack gap="050">
                                                <Text as="p" variant="bodyMd" fontWeight="semibold" style={{ color: '#2c3e50' }}>
                                                    Analysis Summary
                                                </Text>
                                                <Text as="p" variant="bodySm" tone="subdued">
                                                    {getInsightMessage(evaluationSummary)}
                                                </Text>
                                            </BlockStack>
                                        </InlineStack>
                                    </div>
                                </>
                            ) : (
                                // Empty state with soft colors
                                <div style={{ textAlign: 'center', padding: 48, background: '#fafbfc', borderRadius: 12, border: '1px solid #e8ecef' }}>
                                    <div style={{ fontSize: 48, marginBottom: 16, opacity: 0.6 }}>📊</div>
                                    <Text as="p" variant="bodyLg" fontWeight="semibold" style={{ color: '#4a5568' }}>
                                        No messages evaluated yet
                                    </Text>
                                    <Text as="p" variant="bodySm" tone="subdued" style={{ marginTop: 8 }}>
                                        Click "Evaluate Message" on any assistant response to start measuring quality
                                    </Text>
                                    <div style={{ marginTop: 24 }}>
                                        <Badge tone="info">Tip: Start with a few messages to see patterns</Badge>
                                    </div>
                                </div>
                            )}
                        </BlockStack>
                    </Card>
                </Layout.Section>

                {/* Chat Transcript */}
                <Layout.Section>
                    <Card>
                        <BlockStack gap="300">
                            <InlineStack align="space-between" blockAlign="center">
                                <InlineStack gap="200" blockAlign="center">
                                    <MessageCircleIcon size={18} color="#5c6ac4" />
                                    <Text as="h2" variant="headingMd">Chat Transcript</Text>
                                </InlineStack>
                                <Badge tone="info" size="medium">
                                    {messages.filter(m => m.role === 'assistant').length} responses · {messages.length} total
                                </Badge>
                            </InlineStack>
                            <Divider />

                            {/* Chat Controls */}
                            <div style={{
                                display: 'flex',
                                justifyContent: 'space-between',
                                alignItems: 'center',
                                padding: '8px 12px',
                                background: '#f7f8f9',
                                borderRadius: 8,
                                border: '1px solid #e8ecef',
                            }}>
                                <InlineStack gap="200">
                                    <Button
                                        size="slim"
                                        onClick={() => {
                                            const container = document.getElementById('chat-container');
                                            if (container) container.scrollTop = container.scrollHeight;
                                        }}
                                        icon={() => <span style={{ fontSize: 14 }}>⬇️</span>}
                                    >
                                        Scroll to bottom
                                    </Button>
                                    <Button
                                        size="slim"
                                        onClick={() => {
                                            const container = document.getElementById('chat-container');
                                            if (container) container.scrollTop = 0;
                                        }}
                                        icon={() => <span style={{ fontSize: 14 }}>⬆️</span>}
                                    >
                                        Scroll to top
                                    </Button>
                                </InlineStack>
                                <Text as="p" variant="bodySm" tone="subdued">
                                    💡 Click "Evaluate Message" on AI responses to analyze quality
                                </Text>
                            </div>

                            {/* Messages Container */}
                            <div
                                id="chat-container"
                                style={{
                                    display: 'flex',
                                    flexDirection: 'column',
                                    gap: 24,
                                    maxHeight: 550,
                                    overflowY: 'auto',
                                    padding: '16px 12px',
                                    background: '#fafbfc',
                                    borderRadius: 12,
                                    border: '1px solid #e8ecef',
                                }}
                            >
                                {messages.length === 0 ? (
                                    <div style={{ textAlign: 'center', padding: 60, color: '#8c9196' }}>
                                        <MessageCircleIcon size={40} />
                                        <Text as="p" variant="bodyMd" style={{ marginTop: 16 }}>
                                            No messages in this conversation
                                        </Text>
                                    </div>
                                ) : (
                                    messages.map((msg, idx) => (
                                        <div key={msg.id}>
                                            <MessageBubble
                                                msg={msg}
                                                onEvaluate={evaluateMessage}
                                                evaluating={evaluating}
                                                isEvaluating={selectedMessageId === msg.id}
                                                onSubmitFeedback={onSubmitFeedback}
                                            />
                                            {/* Show separator between message pairs */}
                                            {msg.role === 'assistant' && idx < messages.length - 1 && (
                                                <div style={{
                                                    marginTop: 16,
                                                    textAlign: 'center',
                                                    position: 'relative',
                                                }}>
                                                    <div style={{
                                                        height: 1,
                                                        background: 'linear-gradient(90deg, transparent, #e1e3e5, transparent)',
                                                        margin: '8px 0'
                                                    }} />
                                                </div>
                                            )}
                                        </div>
                                    ))
                                )}
                            </div>
                        </BlockStack>
                    </Card>
                </Layout.Section>

                {/* Sidebar Info */}
                {/* Sidebar Info */}
                <Layout.Section variant="oneThird">
                    {/* Conversation Info Card */}
                    <Card>
                        <BlockStack gap="300">
                            <InlineStack gap="200" blockAlign="center">
                                <div style={{
                                    width: 32,
                                    height: 32,
                                    borderRadius: 8,
                                    background: '#e8f0f7',
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                }}>
                                    <span style={{ fontSize: 16 }}>ℹ️</span>
                                </div>
                                <Text as="h2" variant="headingMd">Conversation Info</Text>
                            </InlineStack>
                            <Divider />

                            <BlockStack gap="300">
                                {/* Session Duration */}
                                <div style={{
                                    padding: 12,
                                    background: '#f7f8f9',
                                    borderRadius: 8,
                                    border: '1px solid #e8ecef',
                                }}>
                                    <InlineStack gap="200" blockAlign="center">
                                        <ClockIcon size={16} color="#5c6ac4" />
                                        <BlockStack gap="050">
                                            <Text as="p" variant="bodySm" fontWeight="semibold">Started</Text>
                                            <Text as="p" variant="bodySm" tone="subdued">
                                                {conversation.created_at ? new Date(conversation.created_at).toLocaleString() : 'Unknown'}
                                            </Text>
                                        </BlockStack>
                                    </InlineStack>
                                    {conversation.session_duration_s && conversation.session_duration_s > 0 && (
                                        <div style={{ marginTop: 8, paddingLeft: 24 }}>
                                            <Text as="p" variant="bodySm" tone="subdued">
                                                Duration: {Math.floor(conversation.session_duration_s / 60)}m {conversation.session_duration_s % 60}s
                                            </Text>
                                        </div>
                                    )}
                                </div>

                                {/* Message Stats */}
                                <div style={{
                                    padding: 12,
                                    background: '#f7f8f9',
                                    borderRadius: 8,
                                    border: '1px solid #e8ecef',
                                }}>
                                    <InlineStack gap="200" blockAlign="center">
                                        <MessageCircleIcon size={16} color="#5c6ac4" />
                                        <BlockStack gap="050">
                                            <Text as="p" variant="bodySm" fontWeight="semibold">Message Stats</Text>
                                            <div style={{ display: 'flex', gap: 16, marginTop: 4 }}>
                                                <div>
                                                    <Text as="p" variant="headingMd" fontWeight="bold">{messages.filter(m => m.role === 'user').length}</Text>
                                                    <Text as="p" variant="bodySm" tone="subdued">Customer</Text>
                                                </div>
                                                <div>
                                                    <Text as="p" variant="headingMd" fontWeight="bold">{messages.filter(m => m.role === 'assistant').length}</Text>
                                                    <Text as="p" variant="bodySm" tone="subdued">Assistant</Text>
                                                </div>
                                                <div>
                                                    <Text as="p" variant="headingMd" fontWeight="bold">{conversation.message_count || messages.length}</Text>
                                                    <Text as="p" variant="bodySm" tone="subdued">Total</Text>
                                                </div>
                                            </div>
                                        </BlockStack>
                                    </InlineStack>
                                </div>

                                {/* Status & Intent */}
                                <div style={{
                                    padding: 12,
                                    background: '#f7f8f9',
                                    borderRadius: 8,
                                    border: '1px solid #e8ecef',
                                }}>
                                    <BlockStack gap="200">
                                        <InlineStack gap="200" blockAlign="center">
                                            {conversation.resolved ? (
                                                <CheckCircleIcon size={16} color="#008060" />
                                            ) : (
                                                <CircleIcon size={16} color="#e6a017" />
                                            )}
                                            <BlockStack gap="050">
                                                <Text as="p" variant="bodySm" fontWeight="semibold">Status</Text>
                                                <Badge tone={conversation.resolved ? 'success' : 'warning'}>
                                                    {conversation.outcome || (conversation.resolved ? 'Resolved' : 'Active')}
                                                </Badge>
                                            </BlockStack>
                                        </InlineStack>

                                        <Divider />

                                        <InlineStack gap="200" blockAlign="center">
                                            <ZapIcon size={16} color="#5c6ac4" />
                                            <BlockStack gap="050">
                                                <Text as="p" variant="bodySm" fontWeight="semibold">Intent</Text>
                                                <Badge tone="info">{conversation.intent || 'General'}</Badge>
                                            </BlockStack>
                                        </InlineStack>
                                    </BlockStack>
                                </div>
                            </BlockStack>
                        </BlockStack>
                    </Card>

                    {/* Customer Info Card */}
                    <div style={{ marginTop: '12px' }}>
                        <Card>
                            <BlockStack gap="300">
                                <InlineStack gap="200" blockAlign="center">
                                    <div style={{
                                        width: 32,
                                        height: 32,
                                        borderRadius: 8,
                                        background: '#f0f4f0',
                                        display: 'flex',
                                        alignItems: 'center',
                                        justifyContent: 'center',
                                    }}>
                                        <span style={{ fontSize: 16 }}>👤</span>
                                    </div>
                                    <Text as="h2" variant="headingMd">Customer</Text>
                                </InlineStack>
                                <Divider />

                                <BlockStack gap="200">
                                    <div style={{
                                        padding: 12,
                                        background: '#f7f8f9',
                                        borderRadius: 8,
                                        border: '1px solid #e8ecef',
                                    }}>
                                        <InlineStack gap="200" blockAlign="center">
                                            <MailIcon size={16} color="#5c6ac4" />
                                            <BlockStack gap="050">
                                                <Text as="p" variant="bodySm" fontWeight="semibold">Email</Text>
                                                <Text as="p" variant="bodyMd">
                                                    {conversation.customer_email || 'Anonymous'}
                                                </Text>
                                            </BlockStack>
                                        </InlineStack>
                                    </div>

                                    {conversation.user_uuid && (
                                        <div style={{
                                            padding: 12,
                                            background: '#f7f8f9',
                                            borderRadius: 8,
                                            border: '1px solid #e8ecef',
                                        }}>
                                            <InlineStack gap="200" blockAlign="center">
                                                <span style={{ fontSize: 16 }}>🆔</span>
                                                <BlockStack gap="050">
                                                    <Text as="p" variant="bodySm" fontWeight="semibold">User ID</Text>
                                                    <Text as="p" variant="bodySm" tone="subdued" style={{ wordBreak: 'break-all' }}>
                                                        {conversation.user_uuid}
                                                    </Text>
                                                </BlockStack>
                                            </InlineStack>
                                        </div>
                                    )}

                                    {conversation.return_visit && (
                                        <div style={{
                                            padding: 12,
                                            background: '#eef4ff',
                                            borderRadius: 8,
                                            border: '1px solid #c4e0ff',
                                        }}>
                                            <InlineStack gap="200" blockAlign="center">
                                                <span style={{ fontSize: 16 }}>🔄</span>
                                                <BlockStack gap="050">
                                                    <Text as="p" variant="bodySm" fontWeight="semibold">Return Visitor</Text>
                                                    <Text as="p" variant="bodySm" tone="subdued">
                                                        This customer has interacted with the chatbot before
                                                    </Text>
                                                </BlockStack>
                                            </InlineStack>
                                        </div>
                                    )}
                                </BlockStack>
                            </BlockStack>
                        </Card>
                    </div>
                    {/* Device Info Card */}
                    {/* Device Info Card */}
                    <div style={{ marginTop: '12px', marginBottom: '12px' }}>
                        <Card>
                            <BlockStack gap="300">
                                <InlineStack gap="200" blockAlign="center">
                                    <div style={{
                                        width: 32,
                                        height: 32,
                                        borderRadius: 8,
                                        background: '#f0f4f8',
                                        display: 'flex',
                                        alignItems: 'center',
                                        justifyContent: 'center',
                                    }}>
                                        <span style={{ fontSize: 16 }}>📱</span>
                                    </div>
                                    <Text as="h2" variant="headingMd">Device & Browser</Text>
                                </InlineStack>
                                <Divider />

                                <BlockStack gap="200">
                                    <div style={{
                                        padding: 12,
                                        background: '#f7f8f9',
                                        borderRadius: 8,
                                        border: '1px solid #e8ecef',
                                    }}>
                                        <InlineStack gap="200" blockAlign="center">
                                            {conversation.device_type === 'mobile' ?
                                                <SmartphoneIcon size={16} color="#5c6ac4" /> :
                                                <MonitorIcon size={16} color="#5c6ac4" />
                                            }
                                            <BlockStack gap="050">
                                                <Text as="p" variant="bodySm" fontWeight="semibold">Device Type</Text>
                                                <Badge tone="info">
                                                    {conversation.device_type === 'mobile' ? 'Mobile' :
                                                        conversation.device_type === 'tablet' ? 'Tablet' :
                                                            conversation.device_type === 'desktop' ? 'Desktop' : 'Unknown'}
                                                </Badge>
                                            </BlockStack>
                                        </InlineStack>
                                    </div>

                                    <div style={{
                                        padding: 12,
                                        background: '#f7f8f9',
                                        borderRadius: 8,
                                        border: '1px solid #e8ecef',
                                    }}>
                                        <InlineStack gap="200" blockAlign="center">
                                            <span style={{ fontSize: 16 }}>🌐</span>
                                            <BlockStack gap="050">
                                                <Text as="p" variant="bodySm" fontWeight="semibold">Browser</Text>
                                                <Text as="p" variant="bodyMd">
                                                    {conversation.browser || 'Unknown'}
                                                </Text>
                                            </BlockStack>
                                        </InlineStack>
                                    </div>

                                    {conversation.os && (
                                        <div style={{
                                            padding: 12,
                                            background: '#f7f8f9',
                                            borderRadius: 8,
                                            border: '1px solid #e8ecef',
                                        }}>
                                            <InlineStack gap="200" blockAlign="center">
                                                <span style={{ fontSize: 16 }}>💿</span>
                                                <BlockStack gap="050">
                                                    <Text as="p" variant="bodySm" fontWeight="semibold">Operating System</Text>
                                                    <Text as="p" variant="bodyMd">
                                                        {conversation.os}
                                                    </Text>
                                                </BlockStack>
                                            </InlineStack>
                                        </div>
                                    )}

                                    {conversation.screen_resolution && (
                                        <div style={{
                                            padding: 12,
                                            background: '#f7f8f9',
                                            borderRadius: 8,
                                            border: '1px solid #e8ecef',
                                        }}>
                                            <InlineStack gap="200" blockAlign="center">
                                                <span style={{ fontSize: 16 }}>🖥️</span>
                                                <BlockStack gap="050">
                                                    <Text as="p" variant="bodySm" fontWeight="semibold">Screen Resolution</Text>
                                                    <Text as="p" variant="bodyMd">
                                                        {conversation.screen_resolution}
                                                    </Text>
                                                </BlockStack>
                                            </InlineStack>
                                        </div>
                                    )}

                                    {conversation.language && (
                                        <div style={{
                                            padding: 12,
                                            background: '#f7f8f9',
                                            borderRadius: 8,
                                            border: '1px solid #e8ecef',
                                        }}>
                                            <InlineStack gap="200" blockAlign="center">
                                                <span style={{ fontSize: 16 }}>🔤</span>
                                                <BlockStack gap="050">
                                                    <Text as="p" variant="bodySm" fontWeight="semibold">Language</Text>
                                                    <Text as="p" variant="bodyMd">
                                                        {conversation.language}
                                                    </Text>
                                                </BlockStack>
                                            </InlineStack>
                                        </div>
                                    )}
                                </BlockStack>
                            </BlockStack>
                        </Card>
                    </div>
                    {/* Page URL Card */}
                    {
                        conversation.page_url && (

                            <Card>
                                <BlockStack gap="300">
                                    <InlineStack gap="200" blockAlign="center">
                                        <div style={{
                                            width: 32,
                                            height: 32,
                                            borderRadius: 8,
                                            background: '#f8f4f0',
                                            display: 'flex',
                                            alignItems: 'center',
                                            justifyContent: 'center',
                                        }}>
                                            <span style={{ fontSize: 16 }}>🔗</span>
                                        </div>
                                        <Text as="h2" variant="headingMd">Page URL</Text>
                                    </InlineStack>
                                    <Divider />

                                    <div style={{
                                        padding: 12,
                                        background: '#f7f8f9',
                                        borderRadius: 8,
                                        border: '1px solid #e8ecef',

                                    }}>
                                        <BlockStack gap="300">
                                            <Text as="p" variant="bodySm" tone="subdued" breakWord>
                                                {conversation.page_url}
                                            </Text>
                                            <InlineStack>
                                                <Button
                                                    size="slim"
                                                    onClick={() => window.open(conversation.page_url, '_blank')}
                                                >
                                                    Open in new tab ↗
                                                </Button>
                                            </InlineStack>
                                        </BlockStack>

                                    </div>
                                </BlockStack>
                            </Card>
                        )
                    }
                    <div style={{ marginTop: '12px' }}></div>

                    {/* Quick Actions Card */}
                    <Card>
                        <BlockStack gap="300">
                            <InlineStack gap="200" blockAlign="center">
                                <div style={{
                                    width: 32,
                                    height: 32,
                                    borderRadius: 8,
                                    background: '#f0f4f0',
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                }}>
                                    <span style={{ fontSize: 16 }}>⚡</span>
                                </div>
                                <Text as="h2" variant="headingMd">Quick Actions</Text>
                            </InlineStack>


                            <BlockStack gap="200">

                                <Button
                                    fullWidth

                                    onClick={() => {
                                        navigator.clipboard.writeText(window.location.href);
                                    }}
                                >
                                    Copy conversation link
                                </Button>

                                <Button
                                    fullWidth

                                    tone="critical"
                                    onClick={() => {
                                        if (confirm('Export this conversation to JSON?')) {
                                            const data = {
                                                conversation,
                                                messages,
                                                evaluation_summary: evaluationSummary
                                            };
                                            const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
                                            const url = URL.createObjectURL(blob);
                                            const a = document.createElement('a');
                                            a.href = url;
                                            a.download = `conversation_${conversation.thread_uuid}.json`;
                                            a.click();
                                            URL.revokeObjectURL(url);
                                        }
                                    }}
                                >
                                    Export conversation (JSON)
                                </Button>
                            </BlockStack>
                        </BlockStack>
                    </Card>
                </Layout.Section >
            </Layout >
        </Page >
    );
}