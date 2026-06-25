import { loadingStageMessage, type LoadingStage } from './loadingMessages';

interface LoadingStateProps {
  stage: LoadingStage;
}

export default function LoadingState({ stage }: LoadingStateProps) {
  const message = loadingStageMessage(stage);

  return (
    <div className="space-y-4 py-6">
      {/* Skeleton placeholders */}
      <div className="animate-pulse space-y-3">
        <div className="h-4 bg-gray-200 rounded w-3/4" />
        <div className="h-4 bg-gray-200 rounded w-1/2" />
        <div className="h-4 bg-gray-200 rounded w-5/6" />
      </div>
      <p className="text-sm text-blue-600 font-medium">{message}</p>
    </div>
  );
}
