import type { WorkflowStep } from '../models/aiTypes';

const STEPS: { key: WorkflowStep; label: string }[] = [
  { key: 'input', label: 'Input' },
  { key: 'assumptions', label: 'AI Assumptions' },
  { key: 'review', label: 'Review' },
  { key: 'results', label: 'Results' },
];

const STEP_ORDER: WorkflowStep[] = ['input', 'assumptions', 'review', 'results'];

interface WorkflowStepIndicatorProps {
  currentStep: WorkflowStep;
  onNavigate: (step: WorkflowStep) => void;
}

export default function WorkflowStepIndicator({ currentStep, onNavigate }: WorkflowStepIndicatorProps) {
  const currentIdx = STEP_ORDER.indexOf(currentStep);

  return (
    <nav className="flex items-center justify-center gap-2 mb-8">
      {STEPS.map((s, idx) => {
        const isCompleted = idx < currentIdx;
        const isCurrent = idx === currentIdx;
        const canClick = idx < currentIdx; // backward only

        return (
          <div key={s.key} className="flex items-center">
            <button
              type="button"
              onClick={() => canClick && onNavigate(s.key)}
              disabled={!canClick}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium transition-colors ${
                isCurrent
                  ? 'bg-blue-600 text-white'
                  : isCompleted
                    ? 'bg-green-100 text-green-800 hover:bg-green-200 cursor-pointer'
                    : 'bg-gray-100 text-gray-400 cursor-default'
              }`}
            >
              {isCompleted && <span>✓</span>}
              <span>{idx + 1}. {s.label}</span>
            </button>
            {idx < STEPS.length - 1 && (
              <span className="mx-1 text-gray-300">→</span>
            )}
          </div>
        );
      })}
    </nav>
  );
}
