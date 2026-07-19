"use client";

interface ProgressBarProps {
  progress: number;
  status: string;
  testCount: number;
  crashCount: number;
}

export default function TestCounter({ count }: { count: number }) {
  return (
    <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 flex items-center space-x-4">
      {/* Indeterminate loading spinner */}
      <div className="animate-spin rounded-full h-5 w-5 border-2 border-blue-600 border-t-transparent"></div>
      
      {/* Live count text */}
      <div className="flex-1">
        <p className="text-sm font-medium text-blue-900">
          Fuzzing target API...
        </p>
        <p className="text-xs text-blue-700 mt-1">
          <span className="font-bold text-lg">{count}</span> tests completed
        </p>
      </div>
    </div>
  );
}