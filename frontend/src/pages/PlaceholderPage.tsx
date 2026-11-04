import { Card, EmptyState, PageHeader } from "../components/common/ui";

export function PlaceholderPage({ title, description }: { title: string; description: string }) {
  return (
    <div>
      <PageHeader title={title} />
      <Card>
        <EmptyState title="Coming in the next step" description={description} />
      </Card>
    </div>
  );
}
