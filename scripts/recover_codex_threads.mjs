import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { DatabaseSync } from 'node:sqlite'
import { fileURLToPath } from 'node:url'

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const workspaceRoot = path.resolve(scriptDir, '..')
const codexHome = process.env.CODEX_HOME || path.join(os.homedir(), '.codex')
const stateDbPath = path.join(codexHome, 'state_5.sqlite')
const logsDbPath = path.join(codexHome, 'logs_1.sqlite')
const outputRoot = path.join(workspaceRoot, 'recovery', 'codex_threads')

function ensureDir(dirPath) {
    fs.mkdirSync(dirPath, { recursive: true })
}

function safeFileName(value) {
    return value
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/^-+|-+$/g, '')
        .slice(0, 80) || 'thread'
}

function unixSecondsToIso(value) {
    if (!value) {
        return null
    }

    return new Date(value * 1000).toISOString()
}

function stripDevicePrefix(value) {
    if (typeof value !== 'string') {
        return ''
    }

    return value.startsWith('\\\\?\\') ? value.slice(4) : value
}

function parseWebsocketMessage(rawMessage, prefix) {
    if (!rawMessage?.startsWith(prefix)) {
        return null
    }

    try {
        return JSON.parse(rawMessage.slice(prefix.length))
    } catch {
        return null
    }
}

function extractTextParts(content) {
    if (!Array.isArray(content)) {
        return []
    }

    const parts = []

    for (const item of content) {
        if (!item || typeof item !== 'object') {
            continue
        }

        if (typeof item.text === 'string' && item.text.trim()) {
            parts.push(item.text)
            continue
        }

        if (Array.isArray(item.content)) {
            parts.push(...extractTextParts(item.content))
        }
    }

    return parts
}

function normalizeUserMessages(firstUserMessage, recoveredMessages) {
    const seen = new Set()
    const result = []

    const candidates = [firstUserMessage, ...recoveredMessages]
        .filter((value) => typeof value === 'string')
        .map((value) => value.trim())
        .filter(Boolean)

    for (const candidate of candidates) {
        if (seen.has(candidate)) {
            continue
        }

        seen.add(candidate)
        result.push(candidate)
    }

    return result
}

function collapseWhitespace(value) {
    return value.replace(/\s+/g, ' ').trim()
}

function isEnvironmentContext(value) {
    return /^<environment_context>[\s\S]*<\/environment_context>$/i.test(value.trim())
}

function clipTitle(value) {
    return collapseWhitespace(value).slice(0, 180)
}

function pickPrimaryUserMessage(firstUserMessage, userMessages, fallbackTitle) {
    const candidates = [firstUserMessage, ...userMessages]
        .filter((value) => typeof value === 'string')
        .map((value) => value.trim())
        .filter(Boolean)

    const preferred = candidates.find((value) => !isEnvironmentContext(value))
    return preferred || candidates[0] || fallbackTitle
}

function pickTitle(explicitTitle, firstUserMessage, userMessages, assistantMessages, id) {
    const explicit = typeof explicitTitle === 'string' ? explicitTitle.trim() : ''
    if (explicit) {
        return clipTitle(explicit)
    }

    const primaryUserMessage = pickPrimaryUserMessage(firstUserMessage, userMessages, '')
    if (primaryUserMessage) {
        return clipTitle(primaryUserMessage)
    }

    const firstAssistantLine = assistantMessages
        .map((message) => message.text.trim())
        .filter(Boolean)
        .map((message) => message.split(/\r?\n/, 1)[0]?.trim() || '')
        .find(Boolean)

    if (firstAssistantLine) {
        return clipTitle(firstAssistantLine)
    }

    return `Recovered thread ${id}`
}

function pad2(value) {
    return `${value}`.padStart(2, '0')
}

function buildRolloutPath(threadId, createdAtSeconds) {
    const baseDate = createdAtSeconds ? new Date(createdAtSeconds * 1000) : new Date()
    const year = `${baseDate.getFullYear()}`
    const month = pad2(baseDate.getMonth() + 1)
    const day = pad2(baseDate.getDate())
    const hour = pad2(baseDate.getHours())
    const minute = pad2(baseDate.getMinutes())
    const second = pad2(baseDate.getSeconds())
    const sessionDir = path.join(codexHome, 'sessions', year, month, day)
    const stamp = `${year}-${month}-${day}T${hour}-${minute}-${second}`
    return path.join(sessionDir, `rollout-${stamp}-${threadId}.jsonl`)
}

function renderMarkdown(thread) {
    const lines = []

    lines.push(`# ${thread.title}`)
    lines.push('')
    lines.push(`- Thread id: \`${thread.id}\``)
    lines.push(`- Metadata source: \`${thread.metadataSource}\``)
    lines.push(`- Created at: \`${thread.createdAtIso ?? 'unknown'}\``)
    lines.push(`- Updated at: \`${thread.updatedAtIso ?? 'unknown'}\``)
    lines.push(`- CWD: \`${thread.cwd}\``)
    lines.push(`- Archived: \`${thread.archived}\``)
    lines.push(`- Original rollout path: \`${thread.rolloutPath}\``)
    lines.push(`- Original rollout file present: \`${thread.rolloutFileExists}\``)
    lines.push(`- Original rollout file size: \`${thread.rolloutFileSize}\``)
    lines.push(`- Log rows recovered: \`${thread.logRows}\``)
    lines.push(`- Logs likely truncated: \`${thread.logsLikelyTruncated}\``)
    lines.push(`- Recovery level: \`${thread.recoveryLevel}\``)
    lines.push('')
    lines.push('## User messages')
    lines.push('')

    if (thread.userMessages.length === 0) {
        lines.push('_No user message text recovered._')
    } else {
        for (const [index, userMessage] of thread.userMessages.entries()) {
            lines.push(`### User ${index + 1}`)
            lines.push('')
            lines.push(userMessage)
            lines.push('')
        }
    }

    lines.push('## Assistant messages')
    lines.push('')

    if (thread.assistantMessages.length === 0) {
        lines.push('_No assistant text recovered from logs._')
        lines.push('')
    } else {
        for (const [index, message] of thread.assistantMessages.entries()) {
            lines.push(`### Assistant ${index + 1} (${message.phase})`)
            lines.push('')
            lines.push(message.text || '_Empty_')
            lines.push('')
        }
    }

    lines.push('## Tool calls observed')
    lines.push('')

    if (thread.toolCalls.length === 0) {
        lines.push('_No tool call summary recovered._')
        lines.push('')
    } else {
        for (const [index, toolCall] of thread.toolCalls.entries()) {
            lines.push(`### Tool ${index + 1}`)
            lines.push('')
            lines.push('```text')
            lines.push(toolCall)
            lines.push('```')
            lines.push('')
        }
    }

    return `${lines.join('\n').trim()}\n`
}

function isTitleGeneratorThread(thread) {
    const primaryPrompt = (thread.firstUserMessage || thread.userMessages[0] || '').trim()
    return primaryPrompt.startsWith(
        'You are a helpful assistant. You will be presented with a user prompt, and your job is to provide a short title for a task that will be created from that prompt.',
    )
}

function collectThreadSeeds(stateDb, logsDb) {
    const stateThreads = stateDb
        .prepare(
            `SELECT
                id,
                title,
                first_user_message,
                rollout_path,
                created_at,
                updated_at,
                archived,
                cwd,
                source,
                model_provider,
                sandbox_policy,
                approval_mode,
                cli_version,
                agent_nickname,
                agent_role,
                memory_mode
             FROM threads
             ORDER BY updated_at DESC`,
        )
        .all()
        .map((thread) => ({
            ...thread,
            archived: Boolean(thread.archived),
            cwd: stripDevicePrefix(thread.cwd) || workspaceRoot,
            metadataSource: 'state-db',
        }))

    const knownThreadIds = new Set(stateThreads.map((thread) => thread.id))
    const templateThread = stateThreads[0]

    const logOnlyCandidates = logsDb
        .prepare(
            `SELECT
                thread_id,
                MIN(ts) AS created_at,
                MAX(ts) AS updated_at,
                COUNT(*) AS log_rows,
                SUM(
                    CASE
                        WHEN target = 'codex_api::endpoint::responses_websocket'
                             AND message LIKE 'websocket request:%'
                        THEN 1
                        ELSE 0
                    END
                ) AS request_rows,
                SUM(
                    CASE
                        WHEN target = 'codex_api::endpoint::responses_websocket'
                             AND message LIKE '%response.completed%'
                        THEN 1
                        ELSE 0
                    END
                ) AS completed_rows,
                SUM(
                    CASE
                        WHEN target = 'codex_api::endpoint::responses_websocket'
                             AND message LIKE '%response.output_text.delta%'
                        THEN 1
                        ELSE 0
                    END
                ) AS text_delta_rows
             FROM logs
             WHERE thread_id IS NOT NULL
             GROUP BY thread_id
             ORDER BY updated_at DESC`,
        )
        .all()
        .filter((candidate) => !knownThreadIds.has(candidate.thread_id))
        .filter((candidate) => {
            return (
                candidate.log_rows >= 500 ||
                candidate.request_rows > 0 ||
                candidate.completed_rows > 0 ||
                candidate.text_delta_rows > 50
            )
        })
        .map((candidate) => ({
            id: candidate.thread_id,
            title: '',
            first_user_message: '',
            rollout_path: buildRolloutPath(candidate.thread_id, candidate.created_at),
            created_at: candidate.created_at,
            updated_at: candidate.updated_at,
            archived: false,
            cwd: templateThread?.cwd || workspaceRoot,
            source: 'vscode',
            model_provider: templateThread?.model_provider || 'openai',
            sandbox_policy:
                templateThread?.sandbox_policy ||
                JSON.stringify({
                    type: 'workspace-write',
                    writable_roots: [workspaceRoot],
                    network_access: false,
                    exclude_tmpdir_env_var: false,
                    exclude_slash_tmp: false,
                }),
            approval_mode: templateThread?.approval_mode || 'on-request',
            cli_version: templateThread?.cli_version || '',
            agent_nickname: null,
            agent_role: null,
            memory_mode: templateThread?.memory_mode || 'enabled',
            metadataSource: 'logs-only',
        }))

    return [...stateThreads, ...logOnlyCandidates].sort((a, b) => b.updated_at - a.updated_at)
}

function recoverThreadRecord(threadSeed, logsDb) {
    const logRows = logsDb
        .prepare(
            `SELECT id, ts, target, message
             FROM logs
             WHERE thread_id = ?
             ORDER BY id ASC`,
        )
        .all(threadSeed.id)

    const recoveredUserMessages = []
    const assistantMessageMap = new Map()
    const assistantMessageOrder = []
    const toolCalls = []

    for (const row of logRows) {
        if (!row.message) {
            continue
        }

        if (row.target === 'codex_api::endpoint::responses_websocket') {
            const requestPayload = parseWebsocketMessage(row.message, 'websocket request: ')
            if (requestPayload?.type === 'response.create' && Array.isArray(requestPayload.input)) {
                for (const inputItem of requestPayload.input) {
                    if (inputItem?.type === 'message' && inputItem?.role === 'user') {
                        recoveredUserMessages.push(...extractTextParts(inputItem.content))
                    }
                }
            }

            const eventPayload = parseWebsocketMessage(row.message, 'websocket event: ')
            if (!eventPayload) {
                continue
            }

            if (
                eventPayload.type === 'response.output_item.added' &&
                eventPayload.item?.type === 'message' &&
                eventPayload.item?.role === 'assistant'
            ) {
                const itemId = eventPayload.item.id
                if (!assistantMessageMap.has(itemId)) {
                    assistantMessageMap.set(itemId, {
                        phase: eventPayload.item.phase || 'assistant',
                        text: '',
                        firstLogId: row.id,
                    })
                    assistantMessageOrder.push(itemId)
                }
                continue
            }

            if (eventPayload.type === 'response.output_text.delta' && typeof eventPayload.item_id === 'string') {
                if (!assistantMessageMap.has(eventPayload.item_id)) {
                    assistantMessageMap.set(eventPayload.item_id, {
                        phase: 'assistant',
                        text: '',
                        firstLogId: row.id,
                    })
                    assistantMessageOrder.push(eventPayload.item_id)
                }

                assistantMessageMap.get(eventPayload.item_id).text += eventPayload.delta || ''
                continue
            }

            if (
                eventPayload.type === 'response.output_item.done' &&
                eventPayload.item?.type === 'message' &&
                typeof eventPayload.item?.id === 'string'
            ) {
                const itemId = eventPayload.item.id
                const doneText = extractTextParts(eventPayload.item.content).join('')

                if (!assistantMessageMap.has(itemId)) {
                    assistantMessageMap.set(itemId, {
                        phase: eventPayload.item.phase || 'assistant',
                        text: doneText,
                        firstLogId: row.id,
                    })
                    assistantMessageOrder.push(itemId)
                } else if (!assistantMessageMap.get(itemId).text && doneText) {
                    assistantMessageMap.get(itemId).text = doneText
                }
            }

            continue
        }

        if (row.target === 'codex_core::stream_events_utils' && row.message.startsWith('ToolCall: ')) {
            toolCalls.push(row.message)
        }
    }

    const assistantMessages = assistantMessageOrder
        .map((itemId) => assistantMessageMap.get(itemId))
        .filter(Boolean)
        .map((message) => ({
            phase: message.phase,
            text: message.text.trim(),
            firstLogId: message.firstLogId,
        }))
        .filter((message) => message.text)

    const userMessages = normalizeUserMessages(threadSeed.first_user_message, recoveredUserMessages)
    const title = pickTitle(threadSeed.title, threadSeed.first_user_message, userMessages, assistantMessages, threadSeed.id)
    const firstUserMessage = pickPrimaryUserMessage(threadSeed.first_user_message, userMessages, title)
    const rolloutFileExists = fs.existsSync(threadSeed.rollout_path)
    const rolloutFileSize = rolloutFileExists ? fs.statSync(threadSeed.rollout_path).size : 0
    const logsLikelyTruncated = logRows.length >= 1000

    let recoveryLevel = 'metadata-only'
    if (assistantMessages.length > 0) {
        recoveryLevel = logsLikelyTruncated ? 'partial' : 'substantial'
    } else if (userMessages.length > 0) {
        recoveryLevel = 'prompt-only'
    }

    return {
        id: threadSeed.id,
        title,
        firstUserMessage,
        userMessages,
        assistantMessages,
        toolCalls,
        createdAtIso: unixSecondsToIso(threadSeed.created_at),
        updatedAtIso: unixSecondsToIso(threadSeed.updated_at),
        archived: Boolean(threadSeed.archived),
        cwd: threadSeed.cwd || workspaceRoot,
        rolloutPath: threadSeed.rollout_path,
        rolloutFileExists,
        rolloutFileSize,
        logRows: logRows.length,
        logsLikelyTruncated,
        recoveryLevel,
        metadataSource: threadSeed.metadataSource,
        source: threadSeed.source,
        modelProvider: threadSeed.model_provider,
        sandboxPolicy: threadSeed.sandbox_policy,
        approvalMode: threadSeed.approval_mode,
        cliVersion: threadSeed.cli_version,
        agentNickname: threadSeed.agent_nickname,
        agentRole: threadSeed.agent_role,
        memoryMode: threadSeed.memory_mode,
    }
}

function recoverThreads() {
    if (!fs.existsSync(stateDbPath)) {
        throw new Error(`State database not found: ${stateDbPath}`)
    }

    if (!fs.existsSync(logsDbPath)) {
        throw new Error(`Logs database not found: ${logsDbPath}`)
    }

    fs.rmSync(outputRoot, { recursive: true, force: true })
    ensureDir(outputRoot)

    const stateDb = new DatabaseSync(stateDbPath, { readonly: true })
    const logsDb = new DatabaseSync(logsDbPath, { readonly: true })
    const threadSeeds = collectThreadSeeds(stateDb, logsDb)
    const summary = []
    const sessionIndexLines = []

    for (const threadSeed of threadSeeds) {
        const threadRecord = recoverThreadRecord(threadSeed, logsDb)
        if (isTitleGeneratorThread(threadRecord)) {
            continue
        }

        const fileBase = `${safeFileName(threadRecord.title)}-${threadRecord.id}`

        fs.writeFileSync(path.join(outputRoot, `${fileBase}.json`), `${JSON.stringify(threadRecord, null, 2)}\n`)
        fs.writeFileSync(path.join(outputRoot, `${fileBase}.md`), renderMarkdown(threadRecord))

        summary.push({
            id: threadRecord.id,
            title: threadRecord.title,
            metadataSource: threadRecord.metadataSource,
            createdAtIso: threadRecord.createdAtIso,
            updatedAtIso: threadRecord.updatedAtIso,
            archived: threadRecord.archived,
            recoveryLevel: threadRecord.recoveryLevel,
            rolloutFileExists: threadRecord.rolloutFileExists,
            rolloutFileSize: threadRecord.rolloutFileSize,
            logRows: threadRecord.logRows,
            logsLikelyTruncated: threadRecord.logsLikelyTruncated,
            userMessagesRecovered: threadRecord.userMessages.length,
            assistantMessagesRecovered: threadRecord.assistantMessages.length,
            toolCallsRecovered: threadRecord.toolCalls.length,
        })

        sessionIndexLines.push(
            JSON.stringify({
                id: threadRecord.id,
                thread_name: threadRecord.title,
                updated_at: threadRecord.updatedAtIso,
            }),
        )
    }

    fs.writeFileSync(path.join(outputRoot, 'summary.json'), `${JSON.stringify(summary, null, 2)}\n`)
    fs.writeFileSync(path.join(outputRoot, 'session_index.recovered.jsonl'), `${sessionIndexLines.join('\n')}\n`)

    const readme = [
        '# Codex Thread Recovery',
        '',
        'This folder contains the threads that could be recovered from local Codex databases.',
        '',
        `- Source state DB: \`${stateDbPath}\``,
        `- Source logs DB: \`${logsDbPath}\``,
        '',
        'Files:',
        '- `summary.json`: one-line recovery status per thread',
        '- `session_index.recovered.jsonl`: recovered index that can be inspected manually',
        '- `*.json`: machine-readable recovered thread payload',
        '- `*.md`: readable transcript summary',
        '',
        'Recovery labels:',
        '- `substantial`: metadata plus assistant text from logs, with fewer signs of truncation',
        '- `partial`: metadata plus some assistant text, but logs likely hit the retention cap',
        '- `prompt-only`: only prompt text survived',
        '- `metadata-only`: only thread metadata survived',
        '',
        'Metadata sources:',
        '- `state-db`: thread still existed in the Codex `threads` table',
        '- `logs-only`: thread metadata was reconstructed only from `logs_1.sqlite`',
        '',
        'Note: this export does not modify the live Codex storage.',
        '',
    ].join('\n')

    fs.writeFileSync(path.join(outputRoot, 'README.md'), readme)
}

recoverThreads()
