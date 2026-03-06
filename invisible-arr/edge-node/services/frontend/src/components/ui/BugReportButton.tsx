import React, { useState } from 'react';
import { Bug, X, Send, CheckCircle } from 'lucide-react';
import { useCreateBugReport } from '@/hooks/useBugReport';
import { lastCorrelationId } from '@/api/client';

export default function BugReportButton() {
  const [open, setOpen] = useState(false);
  const [description, setDescription] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const mutation = useCreateBugReport();

  const handleSubmit = () => {
    if (!description.trim()) return;
    mutation.mutate(
      {
        route: window.location.pathname,
        description: description.trim(),
        correlation_id: lastCorrelationId || undefined,
        browser_info: `${navigator.userAgent} | ${window.innerWidth}x${window.innerHeight}`,
      },
      {
        onSuccess: () => {
          setSubmitted(true);
          setDescription('');
          setTimeout(() => {
            setOpen(false);
            setSubmitted(false);
          }, 2000);
        },
      }
    );
  };

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="fixed bottom-20 right-6 md:bottom-6 z-50 p-3 bg-bg-tertiary border border-white/10 rounded-full shadow-lg hover:bg-accent/20 hover:border-accent/40 transition-all"
        title="Report a problem"
      >
        <Bug className="w-5 h-5 text-gray-400" />
      </button>

      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="bg-bg-secondary border border-white/10 rounded-xl w-full max-w-md shadow-2xl">
            <div className="flex items-center justify-between p-4 border-b border-white/10">
              <h3 className="text-lg font-semibold text-white">Report a Problem</h3>
              <button onClick={() => setOpen(false)} className="text-gray-400 hover:text-white">
                <X className="w-5 h-5" />
              </button>
            </div>

            {submitted ? (
              <div className="p-8 text-center">
                <CheckCircle className="w-12 h-12 text-green-500 mx-auto mb-3" />
                <p className="text-white font-medium">Report submitted</p>
                <p className="text-gray-400 text-sm mt-1">Thanks for helping us improve!</p>
              </div>
            ) : (
              <div className="p-4 space-y-4">
                <div>
                  <label className="block text-sm text-gray-400 mb-1">Page</label>
                  <input
                    type="text"
                    value={window.location.pathname}
                    readOnly
                    className="w-full px-3 py-2 bg-bg-primary border border-white/10 rounded-lg text-gray-300 text-sm"
                  />
                </div>
                <div>
                  <label className="block text-sm text-gray-400 mb-1">What went wrong?</label>
                  <textarea
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="Describe the issue..."
                    rows={4}
                    maxLength={5000}
                    className="w-full px-3 py-2 bg-bg-primary border border-white/10 rounded-lg text-white text-sm placeholder-gray-500 resize-none focus:outline-none focus:border-accent/50"
                  />
                </div>
                <button
                  onClick={handleSubmit}
                  disabled={!description.trim() || mutation.isPending}
                  className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-accent text-white rounded-lg hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed transition-colors font-medium"
                >
                  <Send className="w-4 h-4" />
                  {mutation.isPending ? 'Sending...' : 'Submit Report'}
                </button>
                {mutation.isError && (
                  <p className="text-red-400 text-sm text-center">
                    Failed to submit. Please try again.
                  </p>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
