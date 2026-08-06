"use client"
import { useState, useEffect, useRef } from "react"
import type React from "react"

import { supabase } from "@/lib/supabaseClient"
import { v4 as uuidv4 } from "uuid"

const API_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000"

interface Message {
  id?: number
  type: "human" | "ai" | "system"
  content: string
  timestamp?: string
  source?: string  
  isStreaming?: boolean
}

interface Document {
  document_id: string
  filename: string
  file_type: string
  file_size: number
  chunk_count: number
  created_at: string
  is_web_page: boolean
  url?: string
}

interface DocumentListResponse {
  documents: Document[]
  count: number
  max_allowed: number
}

const Chat = () => {
  const [messages, setMessages] = useState<Message[]>([])
  const [inputValue, setInputValue] = useState<string>("")
  const [isLoading, setIsLoading] = useState<boolean>(false)
  const [sessionId, setSessionId] = useState<string>("")
  const [documents, setDocuments] = useState<Document[]>([])
  const [selectedDocumentIds, setSelectedDocumentIds] = useState<string[]>([])
  const [maxDocuments, setMaxDocuments] = useState<number>(10)
  const [isUploadingDoc, setIsUploadingDoc] = useState<boolean>(false)
  const [dragActive, setDragActive] = useState<boolean>(false)
  const [isInitialLoading, setIsInitialLoading] = useState<boolean>(true)
  const [authReady, setAuthReady] = useState<boolean>(false)
  const [streamingMessageId, setStreamingMessageId] = useState<number | null>(null)

  const fileInputRef = useRef<HTMLInputElement>(null)
  const urlInputRef = useRef<HTMLInputElement>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const abortControllerRef = useRef<AbortController | null>(null)
  const isInitialScroll = useRef(true)

  // Wait for Supabase auth to initialize
  useEffect(() => {
    const { data: { subscription } } = supabase.auth.onAuthStateChange(() => {
      setAuthReady(true)
    })

    supabase.auth.getSession().then(() => {
      setAuthReady(true)
    })

    return () => subscription.unsubscribe()
  }, [])

  useEffect(() => {
    if (!authReady) return
    const initializeSession = async () => {
      try {
        setIsInitialLoading(true)
        const existing = localStorage.getItem("chat_session_id")
        let currentSessionId = ""
        
        if (existing) {
          currentSessionId = existing
          setSessionId(existing)
          await loadMessages(existing).catch(() => setMessages([]))
          await loadDocuments(existing)
        } else {
          const newId = uuidv4()
          localStorage.setItem("chat_session_id", newId)
          currentSessionId = newId
          setSessionId(newId)
          await loadMessages(currentSessionId).catch(() => setMessages([]))
        }
      } catch (error) {
        console.error("Failed to initialize session:", error)
        setMessages([])
      } finally {
        setIsInitialLoading(false)
      }
    }
    
    initializeSession()
  }, [authReady])

  const loadMessages = async (sessionId: string) => {
    const { data: { session } } = await supabase.auth.getSession()
    try {
      const response = await fetch(`${API_URL}/api/messages/${sessionId}?limit=50`, {
                headers: {
          Authorization: `Bearer ${session?.access_token}`,
        },
      })
      if (response.ok) {
        const messageHistory = await response.json()
        setMessages(messageHistory)
      } else {
        console.error("Failed to load messages, status:", response.status)
        setMessages([])
      }
    } catch (error) {
      console.error("Failed to load message history:", error)
      setMessages([])
    }
  }

  const loadDocuments = async (sessionId: string) => {
    const { data: { session } } = await supabase.auth.getSession()
    
    try {
      const response = await fetch(`${API_URL}/api/documents/list?session_id=${sessionId}`, {
        headers: {
          Authorization: `Bearer ${session?.access_token}`,
        },
      })
      
      if (response.ok) {
        const data: DocumentListResponse = await response.json()
        setDocuments(data.documents)
        setMaxDocuments(data.max_allowed)
      }
    } catch (error) {
      console.error("Failed to load documents:", error)
    }
  }

  const uploadFile = async (file: File): Promise<void> => {
    const { data: { session } } = await supabase.auth.getSession()
    const formData = new FormData()
    formData.append("file", file)
    formData.append("session_id", sessionId)

    try {
      const res = await fetch(`${API_URL}/api/documents/upload`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${session?.access_token}`,
        },
        body: formData,
      })

      const data = await res.json()
      if (res.ok) {
        const isDuplicate = data.document?.is_duplicate
        const message = isDuplicate 
          ? `ℹ️ "${data.document.filename}" is already in your documents`
          : `✅ Document "${data.document.filename}" uploaded successfully (${data.document.chunk_count} chunks processed)`
        
        setMessages((prev: Message[]) => [
          ...prev,
          {
            type: "system",
            content: message,
            timestamp: new Date().toISOString(),
          },
        ])
        
        // Reload document list (won't add duplicates)
        await loadDocuments(sessionId)
      } else {
        throw new Error(data.detail || "Upload failed")
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : "Unknown error"
      setMessages((prev: Message[]) => [
        ...prev,
        {
          type: "system",
          content: `❌ Upload failed: ${errorMessage}`,
          timestamp: new Date().toISOString(),
        },
      ])
    }
  }

  const uploadUrl = async (url: string): Promise<void> => {
    const { data: { session } } = await supabase.auth.getSession()
    const formData = new FormData()
    formData.append("url", url)
    formData.append("session_id", sessionId)

    try {
      const res = await fetch(`${API_URL}/api/documents/upload`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${session?.access_token}`,
        },
        body: formData,
      })

      const data = await res.json()
      if (res.ok) {
        const isDuplicate = data.document?.is_duplicate
        const message = isDuplicate 
          ? `ℹ️ This URL is already in your documents`
          : `✅ Web page processed successfully (${data.document.chunk_count} chunks)`
        
        setMessages((prev: Message[]) => [
          ...prev,
          {
            type: "system",
            content: message,
            timestamp: new Date().toISOString(),
          },
        ])
        
        // Reload document list (won't add duplicates)
        await loadDocuments(sessionId)
      } else {
        throw new Error(data.detail || "URL processing failed")
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : "Unknown error"
      setMessages((prev: Message[]) => [
        ...prev,
        {
          type: "system",
          content: `❌ URL processing failed: ${errorMessage}`,
          timestamp: new Date().toISOString(),
        },
      ])
    }
  }

  const deleteDocument = async (documentId: string): Promise<void> => {
    const { data: { session } } = await supabase.auth.getSession()
    
    try {
      const res = await fetch(`${API_URL}/api/documents/${documentId}`, {
        method: "DELETE",
        headers: {
          Authorization: `Bearer ${session?.access_token}`,
        },
      })

      const data = await res.json()
      if (res.ok) {
        setMessages((prev: Message[]) => [
          ...prev,
          {
            type: "system",
            content: `🗑️ Document "${data.filename}" removed`,
            timestamp: new Date().toISOString(),
          },
        ])
        
        // Remove from selected if it was selected
        setSelectedDocumentIds(prev => prev.filter(id => id !== documentId))
        
        // Reload document list
        await loadDocuments(sessionId)
      } else {
        throw new Error(data.detail || "Delete failed")
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : "Unknown error"
      setMessages((prev: Message[]) => [
        ...prev,
        {
          type: "system",
          content: `❌ Delete failed: ${errorMessage}`,
          timestamp: new Date().toISOString(),
        },
      ])
    }
  }

  const toggleDocumentSelection = (documentId: string) => {
    setSelectedDocumentIds(prev => {
      if (prev.includes(documentId)) {
        return prev.filter(id => id !== documentId)
      } else {
        return [...prev, documentId]
      }
    })
  }

  const handleDrag = (e: React.DragEvent<HTMLDivElement>): void => {
    e.preventDefault()
    e.stopPropagation()
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true)
    } else if (e.type === "dragleave") {
      setDragActive(false)
    }
  }

  const handleDrop = (e: React.DragEvent<HTMLDivElement>): void => {
    e.preventDefault()
    e.stopPropagation()
    setDragActive(false)

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileUpload(e.dataTransfer.files[0])
    }
  }

  const handleFileUpload = async (file: File): Promise<void> => {
    const allowedTypes = [
      "application/pdf",
      "text/plain",
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      "application/msword",
    ]

    if (!allowedTypes.includes(file.type) && !file.name.match(/\.(pdf|txt|docx|doc)$/i)) {
      alert("Supported formats: PDF, TXT, DOC, DOCX")
      return
    }

    if (file.size > 50 * 1024 * 1024) {
      alert("File size must be less than 50MB")
      return
    }

    if (documents.length >= maxDocuments) {
      alert(`Maximum ${maxDocuments} documents allowed. Please remove some documents first.`)
      return
    }

    setIsUploadingDoc(true)
    await uploadFile(file)
    setIsUploadingDoc(false)
  }

  const handleUrlSubmit = async (url: string): Promise<void> => {
    if (!url.trim()) return

    if (documents.length >= maxDocuments) {
      alert(`Maximum ${maxDocuments} documents allowed. Please remove some documents first.`)
      return
    }

    setIsUploadingDoc(true)
    await uploadUrl(url.trim())
    setIsUploadingDoc(false)
    if (urlInputRef.current) {
      urlInputRef.current.value = ""
    }
  }

  const handleSend = async (): Promise<void> => {
    const { data: { session } } = await supabase.auth.getSession()

    const trimmed = inputValue.trim()
    if (!trimmed || isLoading) return

    const userMessage: Message = { 
      type: "human", 
      content: trimmed,
      timestamp: new Date().toISOString() 
    }
    
    const streamingMessageIndex = messages.length + 1
    const streamingMessage: Message = { 
      id: streamingMessageIndex,
      type: "ai", 
      content: "",
      timestamp: new Date().toISOString(),
      isStreaming: true
    }

    setMessages(prev => [...prev, userMessage, streamingMessage])
    setStreamingMessageId(streamingMessageIndex)
    setInputValue("")
    setIsLoading(true)

    abortControllerRef.current = new AbortController()

    try {
      const response = await fetch(`${API_URL}/api/mentor/enhanced-chat`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${session?.access_token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          message: trimmed,
          session_id: sessionId,
          selected_document_ids: selectedDocumentIds
        }),
        signal: abortControllerRef.current.signal
      })

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }

      const contentType = response.headers.get("content-type")
      const isCached = response.headers.get("X-Cache-Hit") === "true"
      
      if (contentType?.includes("text/event-stream")) {
        const reader = response.body?.getReader()
        const decoder = new TextDecoder()
        let accumulatedContent = ""
        
        if (!reader) {
          throw new Error("No reader available")
        }

        while (true) {
          const { done, value } = await reader.read()
          
          if (done) break

          const chunk = decoder.decode(value)
          const lines = chunk.split('\n')

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const jsonStr = line.slice(6)
                const data = JSON.parse(jsonStr)

                if (data.token) {
                  accumulatedContent += data.token
                  
                  setMessages(prev => 
                    prev.map(msg => 
                      msg.id === streamingMessageIndex
                        ? { ...msg, content: accumulatedContent }
                        : msg
                    )
                  )
                }

                if (data.done) {
                  setMessages(prev => 
                    prev.map(msg => 
                      msg.id === streamingMessageIndex
                        ? { 
                            ...msg, 
                            content: accumulatedContent,
                            isStreaming: false,
                            source: data.cached ? "cache" : "general"
                          }
                        : msg
                    )
                  )
                  
                  if (isCached || data.cached) {
                    console.log("✅ Response served from semantic cache")
                  }
                }

                if (data.error) {
                  throw new Error(data.error)
                }
              } catch (parseError) {
                console.error("Error parsing SSE data:", parseError)
              }
            }
          }
        }

      } else {
        const data = await response.json()
        const responseContent = data.response || "Sorry! I couldn't answer that"
        
        setMessages(prev => 
          prev.map(msg => 
            msg.id === streamingMessageIndex
              ? { 
                  ...msg, 
                  content: responseContent,
                  isStreaming: false,
                  source: data.source
                }
              : msg
          )
        )
      }

    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') {
        console.log("Stream cancelled by user")
      } else {
        console.error("Chat error:", error)
        
        setMessages(prev => 
          prev.map(msg => 
            msg.id === streamingMessageIndex
              ? { 
                  ...msg, 
                  content: "Error connecting to AI. Please try again.",
                  isStreaming: false
                }
              : msg
          )
        )
      }
    } finally {
      setIsLoading(false)
      setStreamingMessageId(null)
      abortControllerRef.current = null
    }
  }

  const cancelStream = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }
  }

  useEffect(() => {
    if (!messagesEndRef.current || messages.length === 0) return;
    
    const isInitial = isInitialScroll.current;
    const delay = isInitialLoading ? 150 : (isInitial ? 100 : 10);
    const behavior = isInitial ? "auto" : "smooth";
    
    setTimeout(() => {
      if (messagesEndRef.current) {
        messagesEndRef.current.scrollIntoView({ 
          behavior,
          block: "end"
        });
        
        if (isInitialScroll.current) {
          isInitialScroll.current = false;
        }
      }
    }, delay);
  }, [messages, isInitialLoading])

  if (isInitialLoading) {
    return (
      <div className="flex items-center justify-center h-[85vh] bg-[#212121] rounded-xl border border-[#333]">
        <div className="text-center">
          <div className="w-16 h-16 border-3 border-gray-700 border-t-gray-400 rounded-full animate-spin mx-auto mb-4"></div>
          <div className="text-xl font-medium text-white mb-2">Initializing...</div>
          <div className="text-sm text-gray-400">Setting up your workspace</div>
        </div>
      </div>
    )
  }

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return bytes + ' B'
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
  }

  return (
    <div className="relative grid lg:grid-cols-[320px_1fr] gap-6 h-[85vh] w-full">
      {/* Left Sidebar - Document & Upload Panel */}
      <div className="bg-[#212121] rounded-xl border border-[#333] p-5 flex flex-col min-h-0">
        <div className="mb-5 flex-shrink-0">
          <h3 className="text-lg font-semibold text-white mb-1">Documents</h3>
          <p className="text-xs text-gray-400">{documents.length}/{maxDocuments} uploaded</p>
        </div>

        {/* Document List */}
        {documents.length > 0 && (
          <div className="flex-1 min-h-0 overflow-y-auto space-y-2 mb-6 pr-2">
            {documents.map((doc) => (
              <div 
                key={doc.document_id}
                className={`p-3 rounded-lg border transition-all cursor-pointer ${
                  selectedDocumentIds.includes(doc.document_id)
                    ? 'border-white bg-[#2a2a2a]'
                    : 'border-[#333] bg-[#1a1a1a] hover:border-[#444] hover:bg-[#252525]'
                }`}
                onClick={() => toggleDocumentSelection(doc.document_id)}
              >
                <div className="flex items-start gap-3">
                  <div className={`w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0 transition-all ${
                    selectedDocumentIds.includes(doc.document_id)
                      ? 'bg-white'
                      : 'bg-[#333]'
                  }`}>
                    {selectedDocumentIds.includes(doc.document_id) ? (
                      <svg className="w-5 h-5 text-black" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                      </svg>
                    ) : (
                      <svg className="w-5 h-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                      </svg>
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-white truncate">{doc.filename}</p>
                    <p className="text-xs text-gray-400 mt-1">
                      {formatFileSize(doc.file_size)} • {doc.chunk_count} chunks
                    </p>
                  </div>
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      deleteDocument(doc.document_id)
                    }}
                    className="text-gray-400 hover:text-red-400 transition-colors p-1"
                  >
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        {selectedDocumentIds.length > 0 && (
          <div className="mb-4 p-3 bg-[#2a2a2a] border border-[#444] rounded-lg">
            <div className="flex items-center gap-2 text-sm text-gray-300">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span>{selectedDocumentIds.length} document{selectedDocumentIds.length > 1 ? 's' : ''} selected for Q&A</span>
            </div>
            <button
              onClick={() => setSelectedDocumentIds([])}
              className="text-xs text-gray-400 hover:text-white mt-1"
            >
              Clear selection
            </button>
          </div>
        )}

        {/* Upload Area */}
        {documents.length < maxDocuments ? (
          <div>
            <div 
              className={`mb-4 p-4 border-2 border-dashed rounded-lg transition-all ${
                dragActive 
                  ? 'border-white bg-[#2a2a2a]' 
                  : 'border-[#444] bg-[#1a1a1a] hover:bg-[#252525]'
              }`}
              onDragEnter={handleDrag}
              onDragLeave={handleDrag}
              onDragOver={handleDrag}
              onDrop={handleDrop}
            >
              <div className="text-center">
                <svg className="w-8 h-8 text-gray-400 mx-auto mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                </svg>
                <p className="text-xs text-gray-300 font-medium">Drag & drop here</p>
              </div>
            </div>

            <div className="space-y-2 flex-1">
              <button
                onClick={() => fileInputRef.current?.click()}
                disabled={isUploadingDoc}
                className="w-full flex items-center justify-center gap-2 bg-white hover:bg-gray-100 text-black rounded-lg px-3 py-2.5 text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
                </svg>
                Upload File
              </button>

              <input
                ref={urlInputRef}
                type="url"
                placeholder="Paste URL"
                className="w-full px-3 py-2 bg-[#2a2a2a] border border-[#444] rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-white focus:border-white transition-all text-sm"
              />
              <button
                onClick={() => handleUrlSubmit(urlInputRef.current?.value || "")}
                disabled={isUploadingDoc}
                className="w-full flex items-center justify-center gap-2 bg-[#2a2a2a] hover:bg-[#333] text-white border border-[#444] rounded-lg px-3 py-2.5 text-sm font-medium transition-colors disabled:opacity-50"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" />
                </svg>
                Add URL
              </button>
            </div>
          </div>
        ) : (
          <div className="p-4 bg-[#2a2a2a] border border-[#444] rounded-lg text-center">
            <p className="text-sm text-gray-300 font-medium mb-2">Document limit reached</p>
            <p className="text-xs text-gray-400">Remove some documents to upload new ones</p>
          </div>
        )}

        <input
          ref={fileInputRef}
          type="file"
          onChange={(e) => {
            const files = e.target.files
            if (files?.[0]) {
              handleFileUpload(files[0])
            }
          }}
          accept=".pdf,.txt,.doc,.docx"
          className="hidden"
        />
      </div>
      {/* Right Panel - Chat Area */}
      <div className="bg-[#212121] rounded-xl border border-[#333] flex flex-col overflow-hidden">
        {/* Chat Header */}
        <div className="p-5 border-b border-[#333] flex-shrink-0">
          <h2 className="text-xl font-semibold text-white mb-1">Chat</h2>
          <p className="text-xs text-gray-400">
            {selectedDocumentIds.length > 0 
              ? `${selectedDocumentIds.length} selected`
              : 'Ask anything'}
          </p>
        </div>

        {/* Messages Area */}
        <div className="flex-1 overflow-y-auto p-6 space-y-5">
          {messages.length === 0 && (
            <div className="flex items-center justify-center h-full">
              <div className="text-center max-w-md">
                <div className="w-16 h-16 bg-white rounded-full flex items-center justify-center mx-auto mb-6">
                  <svg className="w-8 h-8 text-black" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                  </svg>
                </div>
                <h3 className="text-2xl font-semibold text-white mb-3">How can I help you?</h3>
                <p className="text-gray-400">Upload documents and select them to ask questions, or chat normally</p>
              </div>
            </div>
          )}

          {messages.map((msg, i) => (
            <div key={msg.id || i} className={`flex gap-3 items-start ${msg.type === "human" ? "justify-end" : ""}`}>
              {msg.type !== "human" && (
                <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${
                  msg.type === "system"
                    ? "bg-green-600"
                    : "bg-white"
                }`}>
                  {msg.type === "system" ? (
                    <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                  ) : (
                    <svg className="w-5 h-5 text-black" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                    </svg>
                  )}
                </div>
              )}

              <div className={msg.type === "human" ? "max-w-[70%]" : "flex-1 min-w-0"}>
                <div className={`rounded-lg p-4 ${
                  msg.type === "human"
                    ? "bg-white text-black"
                    : msg.type === "system"
                    ? "bg-green-600/20 border border-green-600/30 text-green-200"
                    : "bg-[#2a2a2a] text-white"
                }`}>
                  <div className={`whitespace-pre-wrap text-sm leading-relaxed ${msg.type === "human" ? "text-black" : msg.type === "system" ? "text-green-200" : "text-white"}`}>{msg.content}</div>
                  {msg.isStreaming && (
                    <div className={`flex items-center gap-2 mt-2 text-xs ${msg.type === "human" ? "text-black/70" : "text-gray-400"}`}>
                      <div className="flex gap-1">
                        <div className={`w-2 h-2 rounded-full animate-bounce ${msg.type === "human" ? "bg-black/70" : "bg-gray-400"}`} style={{animationDelay: '0ms'}}></div>
                        <div className={`w-2 h-2 rounded-full animate-bounce ${msg.type === "human" ? "bg-black/70" : "bg-gray-400"}`} style={{animationDelay: '150ms'}}></div>
                        <div className={`w-2 h-2 rounded-full animate-bounce ${msg.type === "human" ? "bg-black/70" : "bg-gray-400"}`} style={{animationDelay: '300ms'}}></div>
                      </div>
                      <span>Thinking...</span>
                    </div>
                  )}
                </div>
                {msg.timestamp && (
                  <div className={`text-xs text-gray-500 mt-1 ${msg.type === "human" ? "text-right mr-1" : "ml-1"}`}>
                    {new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </div>
                )}
              </div>

              {msg.type === "human" && (
                <div className="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 bg-[#444]">
                  <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                  </svg>
                </div>
              )}
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>

        {/* Input Area */}
        <div className="p-5 border-t border-[#333] flex-shrink-0">
          <div className="flex gap-3 items-end">
            <div className="flex-1">
              <textarea
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault()
                    handleSend()
                  }
                }}
                placeholder={
                  selectedDocumentIds.length > 0 
                    ? "Ask about your selected documents..." 
                    : "Type your message..."
                }
                className="w-full px-4 py-3 bg-[#2a2a2a] border border-[#444] rounded-lg text-sm text-white placeholder-gray-500 focus:outline-none focus:border-white transition-all resize-none"
                rows={1}
                style={{ minHeight: '40px', maxHeight: '100px' }}
                disabled={isLoading}
              />
            </div>

            {isLoading && streamingMessageId !== null ? (
              <button
                onClick={cancelStream}
                className="px-5 py-3 bg-white hover:bg-gray-100 text-black rounded-lg font-medium text-sm transition-colors flex items-center gap-2"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 10a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1v-4z" />
                </svg>
                Stop
              </button>
            ) : (
              <button
                onClick={handleSend}
                disabled={isLoading || !inputValue.trim()}
                className="px-5 py-3 bg-white hover:bg-gray-100 text-black rounded-lg font-medium text-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                </svg>
                Send
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

export default Chat
