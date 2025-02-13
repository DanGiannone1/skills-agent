"use client"

import { useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card"
import { Button } from "../../components/ui/button"
import { Lightbulb, Check, Trash2, Undo2, Loader2 } from "lucide-react"
import { motion, AnimatePresence } from "framer-motion"

type Level = "beginner" | "intermediate" | "advanced" | "expert"

type Item = {
  id: string
  name: string
  confidence: number
  level?: Level
  isRejected?: boolean
}

const initialSkills: Item[] = [
  { id: "1", name: "TypeScript", confidence: 95 },
  { id: "2", name: "React Testing", confidence: 88 },
  { id: "3", name: "GraphQL", confidence: 75 },
  { id: "4", name: "Docker", confidence: 65 },
].sort((a, b) => b.confidence - a.confidence)

const initialCompetencies: Item[] = [
  { id: "1", name: "System Design", level: "expert" as Level, confidence: 92 },
  { id: "2", name: "CI/CD", level: "intermediate" as Level, confidence: 85 },
  { id: "3", name: "Cloud Architecture", level: "advanced" as Level, confidence: 78 },
  { id: "4", name: "Agile Methodologies", level: "beginner" as Level, confidence: 70 },
].sort((a, b) => b.confidence - a.confidence)


const levelOrder: Level[] = ["beginner", "intermediate", "advanced", "expert"]

const getLevelColor = (level: Level) => {
  switch (level) {
    case "beginner":
      return "bg-blue-900 text-blue-200"
    case "intermediate":
      return "bg-yellow-900 text-yellow-200"
    case "advanced":
      return "bg-orange-900 text-orange-200"
    case "expert":
      return "bg-red-900 text-red-200"
    default:
      return "bg-gray-700 text-gray-200"
  }
}

export default function RecommendationsPage() {
  const [skills, setSkills] = useState<Item[]>(initialSkills)
  const [competencies, setCompetencies] = useState<Item[]>(initialCompetencies)
  const [isAllApproved, setIsAllApproved] = useState(false)
  const [isApproving, setIsApproving] = useState(false)

  const totalItems = skills.length + competencies.length

  const cycleLevel = (id: string) => {
    setCompetencies((prevCompetencies) =>
      prevCompetencies.map((comp) => {
        if (comp.id === id && comp.level) {
          const currentIndex = levelOrder.indexOf(comp.level)
          const nextIndex = (currentIndex + 1) % levelOrder.length
          return { ...comp, level: levelOrder[nextIndex] }
        }
        return comp
      }),
    )
  }

  const handleReject = (id: string, type: "skills" | "competencies") => {
    const setter = type === "skills" ? setSkills : setCompetencies
    setter((prevItems) => prevItems.map((item) => (item.id === id ? { ...item, isRejected: true } : item)))
  }

  const handleUndo = (id: string, type: "skills" | "competencies") => {
    const setter = type === "skills" ? setSkills : setCompetencies
    setter((prevItems) => prevItems.map((item) => (item.id === id ? { ...item, isRejected: false } : item)))
  }

  const handleApproveAll = () => {
    setIsApproving(true)
    // Animate items disappearing
    setSkills((prevSkills) => prevSkills.map((skill) => ({ ...skill, isApproved: true })))
    setCompetencies((prevCompetencies) => prevCompetencies.map((comp) => ({ ...comp, isApproved: true })))

    // Delay setting all approved to allow for animation
    setTimeout(() => {
      setIsAllApproved(true)
      setIsApproving(false)
    }, 1000) // Adjust timing as needed
  }

  const ItemRow = ({ item, type }: { item: Item; type: "skills" | "competencies" }) => (
    <motion.div
      layout
      initial={{ opacity: 1 }}
      exit={{ opacity: 0, y: -20 }}
      transition={{ duration: 0.5 }}
      className={`flex items-center justify-between py-3 border-b border-gray-800 hover:bg-gray-900/50 rounded-lg px-3 transition-colors ${
        item.isRejected ? "opacity-40" : ""
      }`}
    >
      <span className={`font-medium text-gray-100 ${item.isRejected ? "line-through text-gray-400" : ""}`}>
        {item.name}
      </span>
      <div className="flex items-center gap-3">
        {type === "competencies" && item.level && (
          <button
            onClick={() => cycleLevel(item.id)}
            className={`${getLevelColor(item.level)} px-3 py-1 rounded-full text-xs font-semibold transition-colors duration-200 hover:opacity-90`}
          >
            {item.level}
          </button>
        )}
        <span className="text-sm text-gray-400 min-w-[80px] text-right">{item.confidence}% match</span>
        {item.isRejected ? (
          <Button
            variant="ghost"
            size="icon"
            onClick={() => handleUndo(item.id, type)}
            className="h-8 w-8 rounded-full hover:bg-gray-700/50"
          >
            <Undo2 className="h-4 w-4 text-gray-400 hover:text-purple-400 transition-colors" />
          </Button>
        ) : (
          <Button
            variant="ghost"
            size="icon"
            onClick={() => handleReject(item.id, type)}
            className="h-8 w-8 rounded-full hover:bg-gray-700/50"
          >
            <Trash2 className="h-4 w-4 text-gray-400 hover:text-red-400 transition-colors" />
          </Button>
        )}
      </div>
    </motion.div>
  )

  return (
    <div className="min-h-screen bg-[#121212] flex flex-col">
      <div className="flex-1 mx-auto w-full max-w-6xl p-4 md:p-8 space-y-8">
        <div className="flex items-center justify-between">
          <div className="space-y-1">
            <h1 className="text-4xl font-bold tracking-tight bg-gradient-to-r from-purple-400 to-purple-600 bg-clip-text text-transparent">
              Recommended Profile Updates
            </h1>
            <p className="text-base text-gray-400">
              {isAllApproved ? "No items left to review" : `${totalItems} items to review`}
            </p>
          </div>
          {!isAllApproved && (
            <motion.div whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}>
              <Button
                onClick={handleApproveAll}
                className="bg-purple-600 text-white hover:bg-purple-700 transition-colors px-6 py-2 text-lg shadow-lg shadow-purple-900/20"
                disabled={isApproving}
              >
                {isApproving ? (
                  <>
                    <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                    Approving...
                  </>
                ) : (
                  <>
                    <Check className="mr-2 h-5 w-5" />
                    Approve All
                  </>
                )}
              </Button>
            </motion.div>
          )}
        </div>

        {isAllApproved ? (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            className="text-center py-20 space-y-4"
          >
            <div className="inline-block p-4 rounded-full bg-purple-500/10 mb-4">
              <Check className="h-8 w-8 text-purple-400" />
            </div>
            <h2 className="text-2xl font-bold text-purple-400 mb-2">All items approved!</h2>
            <p className="text-gray-400 max-w-md mx-auto">
              Your profile has been updated with the recommended skills and competencies.
            </p>
          </motion.div>
        ) : (
          <div className="grid gap-8 md:grid-cols-2">
            <Card className="bg-[#1E1E1E] border-gray-800/10 shadow-xl">
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-3 text-xl text-purple-400">
                  <div className="p-2 rounded-lg bg-purple-500/10">
                    <Lightbulb className="h-5 w-5" />
                  </div>
                  Recommended Skills
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <AnimatePresence>
                  {skills.map((skill) => (
                    <ItemRow key={skill.id} item={skill} type="skills" />
                  ))}
                </AnimatePresence>
              </CardContent>
            </Card>

            <Card className="bg-[#1E1E1E] border-gray-800/10 shadow-xl">
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-3 text-xl text-purple-400">
                  <div className="p-2 rounded-lg bg-purple-500/10">
                    <Lightbulb className="h-5 w-5" />
                  </div>
                  Recommended Competencies
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <AnimatePresence>
                  {competencies.map((competency) => (
                    <ItemRow key={competency.id} item={competency} type="competencies" />
                  ))}
                </AnimatePresence>
              </CardContent>
            </Card>
          </div>
        )}
      </div>
    </div>
  )
}

