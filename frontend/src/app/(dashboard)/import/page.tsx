import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { TopBar } from "@/components/layout/topbar";
import { PageHeader, EmptyState } from "@/components/layout/page-header";
import { Upload } from "lucide-react";

export default function ImportPage() {
  return (
    <>
      <TopBar title="Importar" />
      <main className="flex-1 space-y-6 p-4 md:p-6">
        <PageHeader
          title="Importar operações"
          description="Envie notas de corretagem (PDF) ou extratos da B3 (CSV). Os dados são processados localmente."
        />

        <Card>
          <CardHeader>
            <CardTitle className="text-base text-foreground">Arquivos suportados</CardTitle>
            <CardDescription>
              Notas Sinacor (PDF), extrato consolidado da B3 (CSV) e arquivos OFX.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <EmptyState
              title="Arraste seus arquivos aqui"
              description="Ou clique para selecionar. Os arquivos são analisados localmente, no seu computador, e nunca enviados para a nuvem."
            >
              <div className="mt-4 inline-flex items-center gap-2 rounded-md border border-dashed border-border px-4 py-2 text-sm text-muted-foreground">
                <Upload className="h-4 w-4" />
                Aguardando integração com o backend
              </div>
            </EmptyState>
          </CardContent>
        </Card>
      </main>
    </>
  );
}
