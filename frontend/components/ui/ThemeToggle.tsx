'use client';

import * as React from 'react';
import { Moon, Sun } from 'lucide-react';
import { useTheme } from 'next-themes';
import { motion } from 'framer-motion';

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = React.useState(false);

  React.useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) {
    return <div className="w-9 h-9" />; // Placeholder para evitar hydration mismatch
  }

  return (
    <button
      onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
      className="relative p-2 rounded-full hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors"
      aria-label="Toggle theme"
    >
      <div className="relative size-5">
         <motion.div
           initial={false}
           animate={{ scale: theme === 'dark' ? 1 : 0, rotate: theme === 'dark' ? 0 : 90 }}
           transition={{ duration: 0.2 }}
           className="absolute inset-0 flex items-center justify-center"
         >
           <Moon className="size-5 text-white" />
         </motion.div>
         
         <motion.div
            initial={false}
            animate={{ scale: theme === 'light' ? 1 : 0, rotate: theme === 'light' ? 0 : -90 }}
            transition={{ duration: 0.2 }}
            className="absolute inset-0 flex items-center justify-center"
         >
            <Sun className="size-5 text-zinc-900" />
         </motion.div>
      </div>
    </button>
  );
}
