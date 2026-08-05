import { useCallback, useEffect, useState } from "react";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  Stack,
  Switch,
  TextField,
  Typography,
} from "@mui/material";

const API = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1";

type User = { email: string; role: string; name: string };

type LlmItem = {
  id: string;
  name: string;
  provider: string;
  base_url: string;
  model: string;
  active: boolean;
  api_key_set?: boolean;
  api_key_masked?: string | null;
};

type ParserItem = {
  id: string;
  name: string;
  source_code: string;
  base_url: string;
  country_code: string;
  active: boolean;
  token_set?: boolean;
  token_masked?: string | null;
};

type Overview = {
  llm_ready: boolean;
  goszakup_ready: boolean;
};

type Props = {
  token: string;
  user: User;
  onBack: () => void;
};

type LlmForm = {
  name: string;
  provider: string;
  api_key: string;
  base_url: string;
  model: string;
  active: boolean;
};

type ParserForm = {
  name: string;
  source_code: string;
  token: string;
  base_url: string;
  country_code: string;
  active: boolean;
};

const emptyLlm = (): LlmForm => ({
  name: "",
  provider: "openai",
  api_key: "",
  base_url: "https://api.openai.com/v1",
  model: "gpt-5.6-terra",
  active: false,
});

const emptyParser = (): ParserForm => ({
  name: "",
  source_code: "",
  token: "",
  base_url: "https://ows.goszakup.gov.kz",
  country_code: "KZ",
  active: false,
});

function authHeaders(token: string) {
  return { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
}

function rowSx() {
  return {
    display: "grid",
    gridTemplateColumns: { xs: "1fr", sm: "minmax(140px, 1.2fr) minmax(120px, 1fr) 88px auto" },
    gap: 1.5,
    alignItems: "center",
    px: 2,
    py: 1.5,
    bgcolor: "background.paper",
    border: "1px solid",
    borderColor: "divider",
    borderRadius: 1,
  };
}

export default function AdminPanel({ token, user, onBack }: Props) {
  const [llms, setLlms] = useState<LlmItem[]>([]);
  const [parsers, setParsers] = useState<ParserItem[]>([]);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [okMsg, setOkMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [testResult, setTestResult] = useState<string | null>(null);

  const [llmDialog, setLlmDialog] = useState<"create" | LlmItem | null>(null);
  const [llmForm, setLlmForm] = useState<LlmForm>(emptyLlm());
  const [showKey, setShowKey] = useState(false);

  const [parserDialog, setParserDialog] = useState<"create" | ParserItem | null>(null);
  const [parserForm, setParserForm] = useState<ParserForm>(emptyParser());
  const [showToken, setShowToken] = useState(false);

  const [expandedLlm, setExpandedLlm] = useState(true);
  const [expandedParsers, setExpandedParsers] = useState(true);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [iRes, oRes] = await Promise.all([
        fetch(`${API}/admin/integrations`, { headers: authHeaders(token) }),
        fetch(`${API}/admin/overview`, { headers: authHeaders(token) }),
      ]);
      if (iRes.status === 403) throw new Error("Нужна роль admin");
      if (!iRes.ok) throw new Error("Не удалось загрузить интеграции");
      const iJson = await iRes.json();
      setLlms(iJson.llms || []);
      setParsers(iJson.parsers || []);
      if (oRes.ok) setOverview(await oRes.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка загрузки");
    }
  }, [token]);

  useEffect(() => {
    load();
  }, [load]);

  function openCreateLlm() {
    setLlmForm(emptyLlm());
    setShowKey(false);
    setTestResult(null);
    setLlmDialog("create");
  }

  function openEditLlm(item: LlmItem) {
    setLlmForm({
      name: item.name,
      provider: item.provider,
      api_key: "",
      base_url: item.base_url,
      model: item.model,
      active: item.active,
    });
    setShowKey(false);
    setTestResult(null);
    setLlmDialog(item);
  }

  function openCreateParser() {
    setParserForm(emptyParser());
    setShowToken(false);
    setParserDialog("create");
  }

  function openEditParser(item: ParserItem) {
    setParserForm({
      name: item.name,
      source_code: item.source_code,
      token: "",
      base_url: item.base_url,
      country_code: item.country_code,
      active: item.active,
    });
    setShowToken(false);
    setParserDialog(item);
  }

  async function saveLlm() {
    if (!llmForm.name.trim()) {
      setError("Укажите название LLM");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const isCreate = llmDialog === "create";
      const url = isCreate
        ? `${API}/admin/integrations/llms`
        : `${API}/admin/integrations/llms/${(llmDialog as LlmItem).id}`;
      const body: Record<string, unknown> = {
        name: llmForm.name.trim(),
        provider: llmForm.provider.trim(),
        base_url: llmForm.base_url.trim(),
        model: llmForm.model.trim(),
        active: llmForm.active,
      };
      if (llmForm.api_key.trim()) body.api_key = llmForm.api_key.trim();
      if (isCreate && !llmForm.api_key.trim()) {
        setError("Для новой LLM нужен API key");
        setBusy(false);
        return;
      }
      const res = await fetch(url, {
        method: isCreate ? "POST" : "PUT",
        headers: authHeaders(token),
        body: JSON.stringify(body),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Ошибка сохранения LLM");
      setOkMsg(isCreate ? "LLM добавлена" : "LLM обновлена");
      setLlmDialog(null);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка");
    } finally {
      setBusy(false);
    }
  }

  async function saveParser() {
    if (!parserForm.name.trim()) {
      setError("Укажите название сервиса");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const isCreate = parserDialog === "create";
      const url = isCreate
        ? `${API}/admin/integrations/parsers`
        : `${API}/admin/integrations/parsers/${(parserDialog as ParserItem).id}`;
      const body: Record<string, unknown> = {
        name: parserForm.name.trim(),
        source_code: parserForm.source_code.trim() || undefined,
        base_url: parserForm.base_url.trim(),
        country_code: parserForm.country_code.trim(),
        active: parserForm.active,
      };
      if (parserForm.token.trim()) body.token = parserForm.token.trim();
      const res = await fetch(url, {
        method: isCreate ? "POST" : "PUT",
        headers: authHeaders(token),
        body: JSON.stringify(body),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Ошибка сохранения парсера");
      setOkMsg(isCreate ? "Сервис добавлен" : "Сервис обновлён");
      setParserDialog(null);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка");
    } finally {
      setBusy(false);
    }
  }

  async function activateLlm(id: string) {
    setBusy(true);
    try {
      const res = await fetch(`${API}/admin/integrations/llms/${id}/activate`, {
        method: "POST",
        headers: authHeaders(token),
      });
      if (!res.ok) throw new Error("Не удалось активировать");
      setOkMsg("LLM активирована");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка");
    } finally {
      setBusy(false);
    }
  }

  async function activateParser(id: string) {
    setBusy(true);
    try {
      const res = await fetch(`${API}/admin/integrations/parsers/${id}/activate`, {
        method: "POST",
        headers: authHeaders(token),
      });
      if (!res.ok) throw new Error("Не удалось активировать");
      setOkMsg("Парсер активирован");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка");
    } finally {
      setBusy(false);
    }
  }

  async function removeLlm(id: string) {
    if (!confirm("Удалить эту LLM?")) return;
    setBusy(true);
    try {
      const res = await fetch(`${API}/admin/integrations/llms/${id}`, {
        method: "DELETE",
        headers: authHeaders(token),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Не удалось удалить");
      setOkMsg("LLM удалена");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка");
    } finally {
      setBusy(false);
    }
  }

  async function removeParser(id: string) {
    if (!confirm("Удалить этот сервис?")) return;
    setBusy(true);
    try {
      const res = await fetch(`${API}/admin/integrations/parsers/${id}`, {
        method: "DELETE",
        headers: authHeaders(token),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Не удалось удалить");
      setOkMsg("Сервис удалён");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка");
    } finally {
      setBusy(false);
    }
  }

  async function testLlm(id: string) {
    setBusy(true);
    setTestResult(null);
    try {
      const res = await fetch(`${API}/admin/integrations/llms/${id}/test`, {
        method: "POST",
        headers: authHeaders(token),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Тест не прошёл");
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

  async function runIngest(sourceCode: string) {
    setBusy(true);
    try {
      const res = await fetch(`${API}/ingest/sources/${sourceCode}/run`, {
        method: "POST",
        headers: authHeaders(token),
      });
      const data = await res.json();
      setOkMsg(`Crawl: ${data.status}${data.task_id ? ` · ${data.task_id}` : ""}`);
    } catch {
      setError("Не удалось поставить crawl в очередь");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Box sx={{ minHeight: "100vh", bgcolor: "background.default" }}>
      <Box sx={{ px: 3, py: 1.5, borderBottom: "1px solid", borderColor: "divider", bgcolor: "background.paper" }}>
        <Stack direction="row" alignItems="center" spacing={2} flexWrap="wrap">
          <Typography variant="h5">Кабинет администратора</Typography>
          <Chip size="small" color="secondary" label={user.name} />
          <Box sx={{ flex: 1 }} />
          <Button size="small" onClick={onBack}>
            ← К карте
          </Button>
          <Button size="small" variant="outlined" onClick={load} disabled={busy}>
            Обновить
          </Button>
        </Stack>
      </Box>

      <Box sx={{ p: 3, maxWidth: 960, mx: "auto" }}>
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
        {testResult && (
          <Alert
            severity={testResult.startsWith("OK") ? "success" : "warning"}
            sx={{ mb: 2 }}
            onClose={() => setTestResult(null)}
          >
            {testResult}
          </Alert>
        )}

        {overview && (
          <Stack direction="row" gap={1} flexWrap="wrap" mb={2}>
            <Chip
              size="small"
              color={overview.llm_ready ? "success" : "default"}
              label={overview.llm_ready ? "LLM готов" : "LLM без ключа"}
            />
            <Chip
              size="small"
              color={overview.goszakup_ready ? "success" : "default"}
              label={overview.goszakup_ready ? "Парсер готов" : "Парсер без токена"}
            />
          </Stack>
        )}

        <Stack spacing={2}>
          <Accordion expanded={expandedLlm} onChange={(_, v) => setExpandedLlm(v)} disableGutters>
            <AccordionSummary expandIcon={<span>▾</span>}>
              <Stack direction="row" alignItems="center" spacing={1.5} sx={{ width: "100%", pr: 1 }}>
                <Typography variant="subtitle1" fontWeight={600}>
                  LLM
                </Typography>
                <Chip size="small" label={llms.length} />
                <Box sx={{ flex: 1 }} />
                <Button
                  size="small"
                  variant="contained"
                  onClick={(e) => {
                    e.stopPropagation();
                    openCreateLlm();
                  }}
                >
                  + Добавить
                </Button>
              </Stack>
            </AccordionSummary>
            <AccordionDetails>
              <Stack spacing={1}>
                {llms.map((item) => (
                  <Box key={item.id} sx={rowSx()}>
                    <Typography fontWeight={600}>{item.name}</Typography>
                    <Typography variant="body2" color="text.secondary">
                      {item.api_key_set ? item.api_key_masked : "токен не задан"}
                    </Typography>
                    <Chip
                      size="small"
                      color={item.active ? "success" : "default"}
                      label={item.active ? "active" : "выкл"}
                      variant={item.active ? "filled" : "outlined"}
                    />
                    <Stack direction="row" gap={0.5} flexWrap="wrap" justifyContent={{ sm: "flex-end" }}>
                      {!item.active && (
                        <Button size="small" onClick={() => activateLlm(item.id)} disabled={busy}>
                          Активировать
                        </Button>
                      )}
                      <Button size="small" variant="outlined" onClick={() => openEditLlm(item)}>
                        Изменить
                      </Button>
                      <Button size="small" onClick={() => testLlm(item.id)} disabled={busy || !item.api_key_set}>
                        Тест
                      </Button>
                      <Button size="small" color="error" onClick={() => removeLlm(item.id)} disabled={busy || llms.length <= 1}>
                        Удалить
                      </Button>
                    </Stack>
                  </Box>
                ))}
                {llms.length === 0 && (
                  <Typography variant="body2" color="text.secondary">
                    Нет LLM — нажмите «+ Добавить».
                  </Typography>
                )}
              </Stack>
            </AccordionDetails>
          </Accordion>

          <Accordion expanded={expandedParsers} onChange={(_, v) => setExpandedParsers(v)} disableGutters>
            <AccordionSummary expandIcon={<span>▾</span>}>
              <Stack direction="row" alignItems="center" spacing={1.5} sx={{ width: "100%", pr: 1 }}>
                <Typography variant="subtitle1" fontWeight={600}>
                  Сервисы парсинга
                </Typography>
                <Chip size="small" label={parsers.length} />
                <Box sx={{ flex: 1 }} />
                <Button
                  size="small"
                  variant="contained"
                  onClick={(e) => {
                    e.stopPropagation();
                    openCreateParser();
                  }}
                >
                  + Добавить
                </Button>
              </Stack>
            </AccordionSummary>
            <AccordionDetails>
              <Stack spacing={1}>
                {parsers.map((item) => (
                  <Box key={item.id} sx={rowSx()}>
                    <Typography fontWeight={600}>{item.name}</Typography>
                    <Typography variant="body2" color="text.secondary">
                      {item.token_set ? item.token_masked : "токен не задан"}
                    </Typography>
                    <Chip
                      size="small"
                      color={item.active ? "success" : "default"}
                      label={item.active ? "active" : "выкл"}
                      variant={item.active ? "filled" : "outlined"}
                    />
                    <Stack direction="row" gap={0.5} flexWrap="wrap" justifyContent={{ sm: "flex-end" }}>
                      {!item.active && (
                        <Button size="small" onClick={() => activateParser(item.id)} disabled={busy}>
                          Активировать
                        </Button>
                      )}
                      <Button size="small" variant="outlined" onClick={() => openEditParser(item)}>
                        Изменить
                      </Button>
                      <Button size="small" onClick={() => runIngest(item.source_code)} disabled={busy}>
                        Crawl
                      </Button>
                      <Button
                        size="small"
                        color="error"
                        onClick={() => removeParser(item.id)}
                        disabled={busy || parsers.length <= 1}
                      >
                        Удалить
                      </Button>
                    </Stack>
                  </Box>
                ))}
                {parsers.length === 0 && (
                  <Typography variant="body2" color="text.secondary">
                    Нет сервисов — нажмите «+ Добавить».
                  </Typography>
                )}
              </Stack>
            </AccordionDetails>
          </Accordion>
        </Stack>
      </Box>

      <Dialog open={!!llmDialog} onClose={() => setLlmDialog(null)} fullWidth maxWidth="sm">
        <DialogTitle>{llmDialog === "create" ? "Добавить LLM" : "Изменить LLM"}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="Название"
              value={llmForm.name}
              onChange={(e) => setLlmForm({ ...llmForm, name: e.target.value })}
              fullWidth
              required
              placeholder="OpenAI / DeepSeek / OpenRouter"
            />
            <TextField
              label="Токен (API key)"
              type={showKey ? "text" : "password"}
              value={llmForm.api_key}
              onChange={(e) => setLlmForm({ ...llmForm, api_key: e.target.value })}
              fullWidth
              required={llmDialog === "create"}
              placeholder="sk-..."
              helperText={
                llmDialog && llmDialog !== "create" && llmDialog.api_key_set
                  ? `Сейчас: ${llmDialog.api_key_masked} — пусто = не менять`
                  : undefined
              }
            />
            <Button size="small" onClick={() => setShowKey((v) => !v)} sx={{ alignSelf: "flex-start" }}>
              {showKey ? "Скрыть" : "Показать"} токен
            </Button>
            <TextField
              label="Модель"
              value={llmForm.model}
              onChange={(e) => setLlmForm({ ...llmForm, model: e.target.value })}
              fullWidth
              placeholder="gpt-5.6-terra"
            />
            <TextField
              label="Base URL"
              value={llmForm.base_url}
              onChange={(e) => setLlmForm({ ...llmForm, base_url: e.target.value })}
              fullWidth
            />
            <TextField
              label="Provider"
              value={llmForm.provider}
              onChange={(e) => setLlmForm({ ...llmForm, provider: e.target.value })}
              fullWidth
            />
            <FormControlLabel
              control={<Switch checked={llmForm.active} onChange={(_, v) => setLlmForm({ ...llmForm, active: v })} />}
              label="Сделать активной"
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setLlmDialog(null)}>Отмена</Button>
          <Button variant="contained" onClick={saveLlm} disabled={busy}>
            Сохранить
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={!!parserDialog} onClose={() => setParserDialog(null)} fullWidth maxWidth="sm">
        <DialogTitle>{parserDialog === "create" ? "Добавить сервис" : "Изменить сервис"}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="Название"
              value={parserForm.name}
              onChange={(e) => setParserForm({ ...parserForm, name: e.target.value })}
              fullWidth
              required
              placeholder="Goszakup KZ"
            />
            <TextField
              label="Токен"
              type={showToken ? "text" : "password"}
              value={parserForm.token}
              onChange={(e) => setParserForm({ ...parserForm, token: e.target.value })}
              fullWidth
              helperText={
                parserDialog && parserDialog !== "create" && parserDialog.token_set
                  ? `Сейчас: ${parserDialog.token_masked} — пусто = не менять`
                  : undefined
              }
            />
            <Button size="small" onClick={() => setShowToken((v) => !v)} sx={{ alignSelf: "flex-start" }}>
              {showToken ? "Скрыть" : "Показать"} токен
            </Button>
            <TextField
              label="Source code"
              value={parserForm.source_code}
              onChange={(e) => setParserForm({ ...parserForm, source_code: e.target.value })}
              fullWidth
              placeholder="KZ_GOSZAKUP_OWS_V3"
            />
            <TextField
              label="Base URL"
              value={parserForm.base_url}
              onChange={(e) => setParserForm({ ...parserForm, base_url: e.target.value })}
              fullWidth
            />
            <TextField
              label="Страна"
              value={parserForm.country_code}
              onChange={(e) => setParserForm({ ...parserForm, country_code: e.target.value })}
              fullWidth
              sx={{ maxWidth: 120 }}
            />
            <FormControlLabel
              control={
                <Switch checked={parserForm.active} onChange={(_, v) => setParserForm({ ...parserForm, active: v })} />
              }
              label="Сделать активным"
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setParserDialog(null)}>Отмена</Button>
          <Button variant="contained" onClick={saveParser} disabled={busy}>
            Сохранить
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
