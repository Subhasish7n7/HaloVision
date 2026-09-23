import { useNavigate } from "react-router-dom"

export default function Footer() {
  const navigate = useNavigate()

  return (
    <footer className="border-t border-white/5 bg-black">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12 lg:py-16">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-8">
          <div className="md:col-span-2">
            <div className="flex items-center gap-2 mb-4">
              <div className="w-8 h-8 rounded-full bg-gradient-to-br from-gold to-gold-dark flex items-center justify-center">
                <span className="text-black font-bold text-sm">H</span>
              </div>
              <span className="font-poppins font-semibold text-lg text-white">Halo Vision</span>
            </div>
            <p className="text-white/40 text-sm max-w-md">
              An advanced smart glasses platform leveraging real-time machine-learning computer vision technology to empower visually impaired individuals with contextual awareness, navigation, and environmental insights.
            </p>
          </div>

          <div>
            <h4 className="font-semibold text-sm text-white mb-4">Product</h4>
            <ul className="space-y-2">
              {[
                { label: "Features", path: "/features/navigation" },
                { label: "Navigation", path: "/features/navigation" },
                { label: "Search", path: "/features/search" },
                { label: "Voice Command", path: "/features/voice" },
              ].map((item) => (
                <li key={item.label}>
                  <button
                    onClick={() => navigate(item.path)}
                    className="text-sm text-white/40 hover:text-gold transition-colors"
                  >
                    {item.label}
                  </button>
                </li>
              ))}
            </ul>
          </div>

          <div>
            <h4 className="font-semibold text-sm text-white mb-4">Company</h4>
            <ul className="space-y-2">
              {[
                { label: "About", path: "/about" },
                { label: "Mission", path: "/mission" },
                { label: "Home", path: "/" },
                { label: "Contact", path: "/contact" },
              ].map((item) => (
                <li key={item.label}>
                  <button
                    onClick={() => navigate(item.path)}
                    className="text-sm text-white/40 hover:text-gold transition-colors"
                  >
                    {item.label}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </div>

        <div className="mt-12 pt-8 border-t border-white/5 flex flex-col sm:flex-row items-center justify-between gap-4">
          <p className="text-xs text-white/30">
            &copy; 2026 Halo Vision. All rights reserved.
          </p>
        </div>
      </div>
    </footer>
  )
}
