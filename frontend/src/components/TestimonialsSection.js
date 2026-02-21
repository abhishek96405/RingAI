import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Card } from "@/components/ui/card";
import { ChevronLeft, ChevronRight, Star, Quote } from "lucide-react";

const testimonials = [
  {
    quote: "Our communication with guests has increased exponentially with ringAI, especially during off-peak times that we've never had before.",
    author: "Maria Rodriguez",
    role: "General Manager",
    restaurant: "Bella Vista Fine Dining",
    rating: 5,
    image: "https://images.pexels.com/photos/19595138/pexels-photo-19595138.jpeg",
  },
  {
    quote: "Before ringAI, it wasn't uncommon to have customers hang up out of frustration. That's no longer a problem. It handles all of our incoming calls beautifully.",
    author: "James Chen",
    role: "Events & Reservations Manager",
    restaurant: "Golden Dragon Bistro",
    rating: 5,
    image: "https://images.unsplash.com/photo-1676471932681-45fa972d848a",
  },
  {
    quote: "ringAI saves my team over a hundred hours per month! Even with staffing better than before, my staff would boycott me if we stopped using it.",
    author: "David Thompson",
    role: "Operating Manager",
    restaurant: "The Rustic Kitchen",
    rating: 5,
    image: "https://images.pexels.com/photos/4254255/pexels-photo-4254255.jpeg",
  },
];

export const TestimonialsSection = () => {
  const [current, setCurrent] = useState(0);

  const next = () => setCurrent((prev) => (prev + 1) % testimonials.length);
  const prev = () => setCurrent((prev) => (prev - 1 + testimonials.length) % testimonials.length);

  const t = testimonials[current];

  return (
    <section className="py-24 lg:py-32 bg-gradient-subtle">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.6 }}
          className="text-center max-w-2xl mx-auto mb-16"
        >
          <span className="text-sm font-medium text-primary tracking-wide uppercase">
            Testimonials
          </span>
          <h2 className="mt-3 text-3xl sm:text-4xl lg:text-5xl font-heading font-bold text-foreground leading-tight">
            Loved by Restaurant Teams
          </h2>
        </motion.div>

        <div className="max-w-4xl mx-auto">
          <Card className="relative overflow-hidden border-border bg-card">
            <div className="grid md:grid-cols-2">
              {/* Image */}
              <div className="relative h-64 md:h-auto">
                <AnimatePresence mode="wait">
                  <motion.img
                    key={current}
                    src={t.image}
                    alt={t.restaurant}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.4 }}
                    className="absolute inset-0 w-full h-full object-cover"
                  />
                </AnimatePresence>
                <div className="absolute inset-0 bg-gradient-to-r from-transparent to-card/20" />
              </div>

              {/* Content */}
              <div className="p-8 lg:p-10 flex flex-col justify-center">
                <Quote className="w-8 h-8 text-primary/20 mb-4" />
                <AnimatePresence mode="wait">
                  <motion.div
                    key={current}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -10 }}
                    transition={{ duration: 0.4 }}
                  >
                    <div className="flex gap-0.5 mb-4">
                      {Array.from({ length: t.rating }).map((_, i) => (
                        <Star key={i} className="w-4 h-4 fill-accent text-accent" />
                      ))}
                    </div>
                    <blockquote className="text-base lg:text-lg text-foreground leading-relaxed italic mb-6">
                      "{t.quote}"
                    </blockquote>
                    <div>
                      <p className="font-heading font-semibold text-foreground">
                        {t.author}
                      </p>
                      <p className="text-sm text-muted-foreground">
                        {t.role}, {t.restaurant}
                      </p>
                    </div>
                  </motion.div>
                </AnimatePresence>

                {/* Navigation */}
                <div className="flex items-center gap-3 mt-8">
                  <button
                    onClick={prev}
                    className="w-9 h-9 rounded-full border border-border flex items-center justify-center text-muted-foreground hover:text-foreground hover:border-foreground transition-colors"
                  >
                    <ChevronLeft className="w-4 h-4" />
                  </button>
                  <div className="flex gap-1.5">
                    {testimonials.map((_, i) => (
                      <button
                        key={i}
                        onClick={() => setCurrent(i)}
                        className={`h-1.5 rounded-full transition-all duration-300 ${
                          i === current
                            ? "w-6 bg-primary"
                            : "w-1.5 bg-border hover:bg-muted-foreground"
                        }`}
                      />
                    ))}
                  </div>
                  <button
                    onClick={next}
                    className="w-9 h-9 rounded-full border border-border flex items-center justify-center text-muted-foreground hover:text-foreground hover:border-foreground transition-colors"
                  >
                    <ChevronRight className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </section>
  );
};
