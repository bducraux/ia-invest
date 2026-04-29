"use client";

import Link from "next/link";
import { useState } from "react";
import { Plus, Trash2, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import {
  useCreateMember,
  useDeleteMember,
  useMembers,
} from "@/lib/queries";
import { useToastContext } from "@/lib/toast-context";

export default function MembersPage() {
  const membersQuery = useMembers();
  const createMember = useCreateMember();
  const deleteMember = useDeleteMember();
  const toast = useToastContext();

  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    id: "",
    name: "",
    displayName: "",
    email: "",
  });

  const members = membersQuery.data ?? [];

  function handleCreate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!form.id.trim() || !form.name.trim()) return;
    createMember.mutate(
      {
        id: form.id.trim(),
        name: form.name.trim(),
        displayName: form.displayName.trim() || undefined,
        email: form.email.trim() || undefined,
      },
      {
        onSuccess: () => {
          toast.success("Membro criado");
          setForm({ id: "", name: "", displayName: "", email: "" });
          setShowForm(false);
        },
        onError: (err: Error) => {
          toast.error(`Erro ao criar membro: ${err.message}`);
        },
      },
    );
  }

  function handleDelete(memberId: string) {
    if (!window.confirm(`Remover o membro ${memberId}?`)) return;
    deleteMember.mutate(memberId, {
      onSuccess: () => toast.success("Membro removido"),
      onError: (err: Error) =>
        toast.error(`Não foi possível remover: ${err.message}`),
    });
  }

  return (
    <main className="flex-1 space-y-6 p-6">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold">
            <Users className="h-6 w-6" /> Membros
          </h1>
          <p className="text-sm text-muted-foreground">
            Pessoas (donos) das carteiras. Cada portfólio pertence a exatamente um membro.
          </p>
        </div>
        <Button onClick={() => setShowForm((s) => !s)} variant="outline">
          <Plus className="mr-2 h-4 w-4" />
          Novo membro
        </Button>
      </header>

      {showForm ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Criar membro</CardTitle>
            <CardDescription>
              O <code>id</code> é usado como nome da pasta em <code>portfolios/&lt;id&gt;/</code>.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form
              onSubmit={handleCreate}
              className="grid grid-cols-1 gap-3 md:grid-cols-2"
            >
              <label className="space-y-1 text-sm">
                <span className="font-medium">ID</span>
                <Input
                  required
                  pattern="[a-z0-9_-]+"
                  value={form.id}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, id: e.target.value.toLowerCase() }))
                  }
                  placeholder="bruno"
                />
              </label>
              <label className="space-y-1 text-sm">
                <span className="font-medium">Nome</span>
                <Input
                  required
                  value={form.name}
                  onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                  placeholder="Bruno"
                />
              </label>
              <label className="space-y-1 text-sm">
                <span className="font-medium">Apelido</span>
                <Input
                  value={form.displayName}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, displayName: e.target.value }))
                  }
                  placeholder="(opcional)"
                />
              </label>
              <label className="space-y-1 text-sm">
                <span className="font-medium">E-mail</span>
                <Input
                  type="email"
                  value={form.email}
                  onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
                  placeholder="(opcional)"
                />
              </label>
              <div className="md:col-span-2 flex justify-end gap-2">
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => setShowForm(false)}
                >
                  Cancelar
                </Button>
                <Button type="submit" disabled={createMember.isPending}>
                  {createMember.isPending ? "Criando..." : "Criar"}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Membro</TableHead>
                <TableHead>E-mail</TableHead>
                <TableHead className="text-right">Carteiras</TableHead>
                <TableHead>Status</TableHead>
                <TableHead aria-label="Ações" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {membersQuery.isLoading ? (
                <TableRow>
                  <TableCell colSpan={5} className="text-center text-muted-foreground">
                    Carregando...
                  </TableCell>
                </TableRow>
              ) : members.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={5} className="text-center text-muted-foreground">
                    Nenhum membro cadastrado.
                  </TableCell>
                </TableRow>
              ) : (
                members.map((member) => (
                  <TableRow key={member.id}>
                    <TableCell>
                      <Link
                        href={`/members/${encodeURIComponent(member.id)}`}
                        className="font-medium hover:underline"
                      >
                        {member.displayName || member.name}
                      </Link>
                      <div className="text-xs text-muted-foreground">{member.id}</div>
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {member.email ?? "—"}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {member.portfolioCount}
                    </TableCell>
                    <TableCell>
                      <Badge variant={member.status === "active" ? "default" : "outline"}>
                        {member.status === "active" ? "Ativo" : "Inativo"}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        variant="ghost"
                        size="icon"
                        title="Remover"
                        disabled={member.portfolioCount > 0 || deleteMember.isPending}
                        onClick={() => handleDelete(member.id)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </main>
  );
}
