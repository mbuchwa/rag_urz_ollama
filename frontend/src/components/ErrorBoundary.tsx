import { Component, ReactNode } from "react";

export class ErrorBoundary extends Component<{ children: ReactNode }, { hasError: boolean }> {
  state = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error: any, info: any) {
    console.error("Chat ErrorBoundary caught:", error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="p-4 text-sm text-red-700 bg-red-50 rounded-lg">
          Something went wrong rendering the chat. Please try again.
        </div>
      );
    }
    return this.props.children;
  }
}
