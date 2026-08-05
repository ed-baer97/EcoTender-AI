import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  IconButton,
  Stack,
  Tab,
  Tabs,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from "@mui/material";

const API = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1";

type User = { email: string; role: string; name: string };

type SecretItem = {
  key: string;
  label: string;
  category: string;
  secret: boolean;
  description: string;
  placeholder?: string;
  configured: boolean;
  source: string;
  value?: string | null;
  value_masked?: string | null;
  updated_at?: string | null;
  updated_by?: string | null;
};

type Overview = {
  services: Record<string, { status?: string; error?: string }>;
  keys_configured: number;
  keys_total: number;
  llm_ready: boolean;
  goszakup_ready: boolean;
};

type AuditItem = { ts: number; action: string; key: string; actor: string; masked?: string };

type Props = {
  token: string;
  user: User;
  onBack: () => void;
};

function authHeaders(token: string) {
  return { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
}

export default function AdminPanel({ token, user, onBack }: Props) {
  const [tab, setTab] = useState(0);
  const [items, setItems] = useState<SecretItem[]>([]);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [audit, setAudit] = useState<AuditItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [okMsg, setOkMsg] = useState<string | null>(null);
  const [edit, setEdit] = useState<SecretItem | null>(null);
  const [value, setValue] = useState("");
  const [showValue, setShowValue] = useState(false);
  const [busy, setBusy] = useState(false);
  const [testResult, setTestResult] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [sRes, oRes, aRes] = await Promise.all([
        fetch(`${API}/admin/secrets`, { headers: authHeaders(token) }),
        fetch(`${API}/admin/overview`, { headers: authHeaders(token) }),
        fetch(`${API}/admin/audit?limit=40`, { headers: authHeaders(token) }),
      ]);
      if (sRes.status === 403) throw new Error("Нужна роль admin");
      if (!sRes.ok) throw new Error("Не удалось загрузить ключи");
      const sJson = await sRes.json();
      setItems(sJson.items || []);
      if (oRes.ok) setOverview(await oRes.json());
      if (aRes.ok) {
        const aJson = await aRes.json();
        setAudit(aJson.items || []);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка загрузки");
    }
  }, [token]);

  useEffect(() => {
    load();
  }, [load]);

  async function saveKey() {
    if (!edit || !value.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`${API}/admin/secrets/${edit.key}`, {
        method: "PUT",
        headers: authHeaders(token),
        body: JSON.stringify({ value: value.trim() }),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail || "Ошибка сохранения");
      }
      setOkMsg(`${edit.key} сохранён — сервисы подхватят без перезапуска`);
      setEdit(null);
      setValue("");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка");
    } finally {
      setBusy(false);
    }
  }

  async function clearKey(key: string) {
    if (!confirm(`Удалить runtime-значение ${key}? Останется только .env (если есть).`)) return;
    setBusy(true);
    try {
      const res = await fetch(`${API}/admin/secrets/${key}`, {
        method: "DELETE",
        headers: authHeaders(token),
      });
      if (!res.ok) throw new Error("Не удалось удалить");
      setOkMsg(`${key} очищен`);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка");
    } finally {
      setBusy(false);
    }
  }

  async function testLlm() {
    setBusy(true);
    setTestResult(null);
    try {
      const res = await fetch(`${API}/admin/secrets/LLM_API_KEY/test`, {
        method: "POST",
        headers: authHeaders(token),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Тест не прошёл");
      setTestResult(
        data.ok
          ? `OK · ${data.model} · ${typeof data.preview === "string" ? data.preview : JSON.stringify(data.preview)}`
          : `HTTP ${data.status_code}: ${JSON.stringify(data.preview)}`
      );
    } catch (e) {
      setTestResult(e instanceof Error ? e.message : "Ошибка теста");
    } finally {
      setBusy(false);
    }
  }

  async function runIngest() {
    setBusy(true);
    try {
      const res = await fetch(`${API}/ingest/sources/KZ_GOSZAKUP_OWS_V3/run`, {
        method: "POST",
        headers: authHeaders(token),
      });
      const data = await res.json();
      setOkMsg(`Ingest: ${data.status}${data.task_id ? ` · task ${data.task_id}` : ""}`);
    } catch {
      setError("Не удалось поставить crawl в очередь");
    } finally {
      setBusy(false);
    }
  }

  const llmKeys = items.filter((i) => i.category === "llm");
  const ingestKeys = items.filter((i) => i.category === "ingestion");

  return (
    <Box sx={{ minHeight: "100vh", bgcolor: "background.default" }}>
      <Box sx={{ px: 3, py: 1.5, borderBottom: "1px solid", borderColor: "divider", bgcolor: "background.paper" }}>
        <Stack direction="row" alignItems="center" spacing={2} flexWrap="wrap">
          <Typography variant="h5">Админка · ключи</Typography>
          <Chip size="small" color="secondary" label={`${user.name} · admin`} />
          <Box sx={{ flex: 1 }} />
          <Button size="small" onClick={onBack}>
            ← К карте
          </Button>
          <Button size="small" variant="outlined" onClick={load} disabled={busy}>
            Обновить
          </Button>
        </Stack>
      </Box>

      <Box sx={{ p: 3, maxWidth: 1100, mx: "auto" }}>
        {error && (
          <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
            {error}
          </Alert>
        )}
        {okMsg && (
          <Alert severity="success" sx={{ mb: 2 }} onClose={() => setOkMsg(null)}>
            {okMsg}
          </Alert>
        )}

        {overview && (
          <Stack direction="row" gap={1} flexWrap="wrap" mb={3}>
            <Chip
              color={overview.llm_ready ? "success" : "default"}
              label={overview.llm_ready ? "LLM ключ есть" : "LLM ключ пуст"}
            />
            <Chip
              color={overview.goszakup_ready ? "success" : "default"}
              label={overview.goszakup_ready ? "Goszakup токен есть" : "Goszakup offline"}
            />
            <Chip label={`ключей: ${overview.keys_configured}/${overview.keys_total}`} />
            {Object.entries(overview.services).map(([name, st]) => (
              <Chip
                key={name}
                size="small"
                variant="outlined"
                color={st.status === "ok" ? "success" : "warning"}
                label={`${name}: ${st.status || "down"}`}
              />
            ))}
          </Stack>
        )}

        <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}>
          <Tab label="Ключи и конфиг" />
          <Tab label="Аудит" />
          <Tab label="Действия" />
        </Tabs>

        {tab === 0 && (
          <Stack spacing={3}>
            <SecretTable
              title="LLM (объяснение Risk Score)"
              items={llmKeys}
              onEdit={(item) => {
                setEdit(item);
                setValue(item.secret ? "" : item.value || "");
                setShowValue(false);
                setTestResult(null);
              }}
              onClear={clearKey}
            />
            <SecretTable
              title="Ingestion (goszakup)"
              items={ingestKeys}
              onEdit={(item) => {
                setEdit(item);
                setValue(item.secret ? "" : item.value || "");
                setShowValue(false);
              }}
              onClear={clearKey}
            />
            <Typography variant="caption" color="text.secondary">
              Runtime-значения пишутся в Redis + data/runtime/config.json и перекрывают .env без recreate контейнеров.
              Секреты в UI маскируются (sk-ab…xyz1).
            </Typography>
          </Stack>
        )}

        {tab === 1 && (
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Время</TableCell>
                <TableCell>Действие</TableCell>
                <TableCell>Ключ</TableCell>
                <TableCell>Кто</TableCell>
                <TableCell>Маска</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {audit.length === 0 && (
                <TableRow>
                  <TableCell colSpan={5}>
                    <Typography variant="body2" color="text.secondary">
                      Пока пусто — сохраните или удалите ключ.
                    </Typography>
                  </TableCell>
                </TableRow>
              )}
              {audit.map((a, i) => (
                <TableRow key={`${a.ts}-${i}`}>
                  <TableCell>{new Date(a.ts * 1000).toLocaleString("ru-RU")}</TableCell>
                  <TableCell>{a.action}</TableCell>
                  <TableCell>
                    <code>{a.key}</code>
                  </TableCell>
                  <TableCell>{a.actor}</TableCell>
                  <TableCell>{a.masked || "—"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}

        {tab === 2 && (
          <Stack spacing={2} maxWidth={480}>
            <Typography variant="body2" color="text.secondary">
              Проверка LLM и запуск парсера после сохранения ключей.
            </Typography>
            <Button variant="contained" onClick={testLlm} disabled={busy}>
              Проверить LLM_API_KEY
            </Button>
            {testResult && <Alert severity={testResult.startsWith("OK") ? "success" : "warning"}>{testResult}</Alert>}
            <Divider />
            <Button variant="outlined" onClick={runIngest} disabled={busy}>
              Запустить crawl goszakup
            </Button>
          </Stack>
        )}
      </Box>

      <Dialog open={!!edit} onClose={() => setEdit(null)} fullWidth maxWidth="sm">
        <DialogTitle>{edit?.label}</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            {edit?.description}
          </Typography>
          {edit?.configured && edit.secret && (
            <Alert severity="info" sx={{ mb: 2 }}>
              Сейчас: {edit.value_masked} · source={edit.source}
            </Alert>
          )}
          <TextField
            autoFocus
            fullWidth
            label={edit?.key}
            placeholder={edit?.placeholder}
            type={edit?.secret && !showValue ? "password" : "text"}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            helperText={edit?.secret ? "Вставьте новый ключ целиком — старый не показывается" : undefined}
          />
          {edit?.secret && (
            <Button size="small" sx={{ mt: 1 }} onClick={() => setShowValue((v) => !v)}>
              {showValue ? "Скрыть" : "Показать"}
            </Button>
          )}
          {edit?.key === "LLM_API_KEY" && (
            <Box sx={{ mt: 2 }}>
              <Button size="small" variant="outlined" onClick={testLlm} disabled={busy || !items.find((i) => i.key === "LLM_API_KEY")?.configured}>
                Тест текущего сохранённого ключа
              </Button>
              {testResult && (
                <Typography variant="caption" display="block" sx={{ mt: 1 }}>
                  {testResult}
                </Typography>
              )}
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEdit(null)}>Отмена</Button>
          <Button variant="contained" onClick={saveKey} disabled={busy || !value.trim()}>
            Сохранить
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

function SecretTable({
  title,
  items,
  onEdit,
  onClear,
}: {
  title: string;
  items: SecretItem[];
  onEdit: (item: SecretItem) => void;
  onClear: (key: string) => void;
}) {
  return (
    <Box>
      <Typography variant="subtitle1" gutterBottom>
        {title}
      </Typography>
      <Table size="small" sx={{ bgcolor: "background.paper", borderRadius: 1 }}>
        <TableHead>
          <TableRow>
            <TableCell>Параметр</TableCell>
            <TableCell>Значение</TableCell>
            <TableCell>Источник</TableCell>
            <TableCell align="right">Действия</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {items.map((item) => (
            <TableRow key={item.key}>
              <TableCell>
                <Typography variant="body2" fontWeight={600}>
                  {item.label}
                </Typography>
                <Typography variant="caption" color="text.secondary" component="div">
                  <code>{item.key}</code>
                </Typography>
              </TableCell>
              <TableCell>
                {item.configured ? (
                  <Chip size="small" color="success" label={item.value_masked || item.value || "set"} />
                ) : (
                  <Chip size="small" label="не задан" variant="outlined" />
                )}
              </TableCell>
              <TableCell>
                <Chip size="small" variant="outlined" label={item.source} />
              </TableCell>
              <TableCell align="right">
                <Button size="small" onClick={() => onEdit(item)}>
                  {item.configured ? "Изменить" : "Добавить"}
                </Button>
                {item.configured && item.source === "runtime" && (
                  <IconButton size="small" onClick={() => onClear(item.key)} aria-label="clear" sx={{ ml: 0.5 }}>
                    <Typography variant="caption" color="error">
                      ✕
                    </Typography>
                  </IconButton>
                )}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Box>
  );
}
